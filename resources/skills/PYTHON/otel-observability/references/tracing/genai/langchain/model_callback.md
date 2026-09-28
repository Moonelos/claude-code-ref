# LangChain Model Callback

One span per **physical** model request, with model identity, parameters, token usage, and — when streaming — time to first chunk.

The callback fires below every middleware, so retries produce separate spans with no retry-specific code.

Two neighbours own what it writes: token counts come from `../token_usage.md`, prompt and completion capture from `../content_capture.md`.

## Contents

- [Model and provider identity](#resolving-model-identity)
- [`LLMResult` metadata](#reading-the-llmresult)
- [The callback](#the-callback)
- [Streaming](#streaming)
- [How to attach it](#how-to-attach-it)
- [Verification](#verify-before-moving-on)

The code fences below are **consecutive partial fragments of one callback
module**, not standalone programs. Before using them, copy
`extract_usage_metadata()` from `../token_usage.md` and import the complete
serializers from `../content_capture.md`; the callback fragments list those
dependencies explicitly.

For provider- and version-specific message or metadata shapes, first read
`provider_compatibility.md` and complete its compatibility gate.

## Resolving model identity

The single most common defect in a hand-written callback is a hardcoded model name. It survives review, then quietly reports `gpt-5` for every call after someone adds a cheaper model for summarization.

`on_chat_model_start` receives the model identity in more than one place depending on the provider and LangChain version, so resolve it with fallbacks:

```python
# observability/genai.py
from typing import Any


def resolve_request_model(
    serialized: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    kwargs: dict[str, Any],
) -> str | None:
    """Best-effort model name from a chat-model start event."""
    metadata = metadata or {}
    # LangChain's standardized metadata is the most reliable source.
    value = metadata.get("ls_model_name")
    if isinstance(value, str) and value:
        return value

    invocation_params = kwargs.get("invocation_params") or {}
    for key in ("model", "model_name", "model_id", "deployment_name"):
        value = invocation_params.get(key)
        if isinstance(value, str) and value:
            return value

    serialized_kwargs = (serialized or {}).get("kwargs") or {}
    for key in ("model", "model_name", "model_id"):
        value = serialized_kwargs.get(key)
        if isinstance(value, str) and value:
            return value

    # ls_model_type is deliberately excluded: it is "chat" or "llm", not a
    # model identifier. Omit the standard attribute when identity is unknown.
    return None


def resolve_provider(metadata: dict[str, Any] | None) -> str:
    """Map LangChain's provider label onto gen_ai.provider.name values."""
    provider = (metadata or {}).get("ls_provider")
    return {
        "openai": "openai",
        # Current LangChain integrations expose these short/legacy labels;
        # normalize them to the OTel well-known provider values.
        "azure": "azure.ai.openai",
        "azure_openai": "azure.ai.openai",
        "anthropic": "anthropic",
        "amazon_bedrock": "aws.bedrock",
        "bedrock": "aws.bedrock",
        "bedrock_converse": "aws.bedrock",
        "google_genai": "gcp.gemini",
        "google_vertexai": "gcp.vertex_ai",
        "cohere": "cohere",
        "mistral": "mistral_ai",
        "mistralai": "mistral_ai",
        "groq": "groq",
        "deepseek": "deepseek",
        "xai": "x_ai",
    }.get(provider, provider or "unknown")
```

Verify the values on a real call before trusting the mapping — print `metadata` once from `on_chat_model_start` and check what your provider integration actually sends.

## Reading the `LLMResult`

`on_llm_end` receives an `LLMResult`, not a message, so both the usage and the response metadata need digging out of the generations list.

`extract_usage_metadata()` — the LangChain adapter for token counts — is specified in **`../token_usage.md`**, alongside the writer it feeds and the adapters for every other source. Its *code* belongs in this module, next to the callback that is its only caller; what lives elsewhere is the contract, not the function. Copy it from there rather than re-deriving the mapping.

Response identity has no such shared home, because it is shaped by the LangChain integration rather than by the provider:

```python
def extract_response_metadata(response: Any) -> dict[str, Any]:
    """Response model, response id, and finish reasons from an LLMResult."""
    result: dict[str, Any] = {}
    finish_reasons: list[str] = []

    for generation_list in getattr(response, "generations", None) or []:
        for generation in generation_list:
            message = getattr(generation, "message", None)
            metadata = getattr(message, "response_metadata", None) or {}

            model = metadata.get("model_name") or metadata.get("model")
            if model and "response_model" not in result:
                result["response_model"] = model

            response_id = getattr(message, "id", None) or metadata.get("id")
            if response_id and "response_id" not in result:
                result["response_id"] = response_id

            generation_info = getattr(generation, "generation_info", None) or {}
            reason = resolve_finish_reason(metadata, generation_info)
            if reason:
                finish_reasons.append(reason)

    if finish_reasons:
        result["finish_reasons"] = finish_reasons
    return result
```

`getattr` with defaults throughout, deliberately. Instrumentation must not be the thing that crashes a request because a provider stopped populating a field.

## The callback

One handler covers both streaming and non-streaming models. It differs in three
places only — the `gen_ai.request.stream` value, the `on_llm_new_token` hook,
and where the captured output text comes from — so two classes would be ~90%
identical code and two places to fix every future bug.

```python
import time
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from observability.agent_counters import current_counters
from observability.genai_attributes import (
    APP_OBSERVATION_INPUT,
    APP_OBSERVATION_OUTPUT,
    APP_INPUT_CAPTURE_MODE,
    ERROR_TYPE,
    GENAI_FINISH_REASONS,
    GENAI_INPUT_MESSAGES,
    GENAI_OPERATION_NAME,
    GENAI_OUTPUT_MESSAGES,
    GENAI_OUTPUT_TYPE,
    GENAI_PROVIDER_NAME,
    GENAI_REQUEST_MODEL,
    GENAI_REQUEST_STREAM,
    GENAI_RESPONSE_ID,
    GENAI_RESPONSE_MODEL,
    GENAI_SYSTEM_INSTRUCTIONS,
)
from observability.genai_content import (
    resolve_finish_reason,
    serialize_chat_model_input,
    serialize_llm_result,
    serialize_observation_input,
    serialize_observation_output,
    serialize_observation_text_output,
    serialize_text_output,
)
from observability.metrics import (
    record_model_operation,
    record_time_to_first_chunk,
)
from observability.genai_usage import set_usage_attributes
from observability.spans import error_type_of, mark_error

tracer = trace.get_tracer(__name__)
MAX_CAPTURED_OUTPUT_CHARS = 32_768


class OTelModelCallback(AsyncCallbackHandler):
    """One span per physical model request.

    Sits below every middleware, so each retry attempt produces its own span.
    Pass streaming=True for a model built with streaming=True; that only sets
    `gen_ai.request.stream` and the chunk-count attribute. Everything the
    stream actually produces is observed, not assumed.
    """

    def __init__(
        self,
        *,
        capture_content: bool,
        streaming: bool = False,
        separate_system_instructions: bool = False,
    ) -> None:
        # Bootstrap passes the settings value; never read settings at import.
        self._capture_content = capture_content
        self._streaming = streaming
        # Set from the concrete provider adapter's wire contract. For example,
        # Bedrock Converse sends system instructions separately from messages.
        self._separate_system_instructions = separate_system_instructions
        # Keyed by run_id: LangChain runs model calls concurrently.
        self._runs: dict[Any, dict[str, Any]] = {}

    async def on_chat_model_start(
        self,
        serialized,
        messages,
        *,
        run_id,
        parent_run_id=None,
        metadata=None,
        **kwargs,
    ) -> None:
        model = resolve_request_model(serialized, metadata, kwargs)
        provider = resolve_provider(metadata)
        span_name = f"chat {model}" if model else "chat"

        counters = current_counters()
        if counters is not None:
            counters.inference_calls += 1

        attributes = {
            GENAI_OPERATION_NAME: "chat",
            GENAI_PROVIDER_NAME: provider,
            GENAI_REQUEST_STREAM: self._streaming,
        }
        if model:
            attributes[GENAI_REQUEST_MODEL] = model

        # Resolve this from the actual callback/provider request shape. Native
        # `json_schema` or `json_object` requests set `gen_ai.output.type=json`;
        # tool calling is not mislabeled as JSON merely because arguments are JSON.
        invocation_params = kwargs.get("invocation_params") or {}
        response_format = invocation_params.get("response_format") or {}
        output_type = None
        if response_format.get("type") in {"json_schema", "json_object"}:
            output_type = "json"
            attributes[GENAI_OUTPUT_TYPE] = output_type

        # start_span (not start_as_current_span): the callback returns before
        # the model call finishes, so this span cannot be a context manager.
        # Its parent is whatever span is current right now — the agent span.
        span = tracer.start_span(
            span_name,
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
        )

        for attribute, key in (
            ("gen_ai.request.temperature", "temperature"),
            ("gen_ai.request.max_tokens", "max_tokens"),
            ("gen_ai.request.top_p", "top_p"),
        ):
            if invocation_params.get(key) is not None:
                span.set_attribute(attribute, invocation_params[key])

        if self._capture_content:
            captured_system, captured_input, batch_size = serialize_chat_model_input(
                messages,
                separate_system_instructions=self._separate_system_instructions,
            )
            if captured_system is not None:
                span.set_attribute(GENAI_SYSTEM_INSTRUCTIONS, captured_system)
            span.set_attribute(GENAI_INPUT_MESSAGES, captured_input)
            span.set_attribute(APP_OBSERVATION_INPUT, serialize_observation_input(messages))
            span.set_attribute("app.gen_ai.input.batch_size", batch_size)
            if batch_size > 1:
                span.set_attribute(APP_INPUT_CAPTURE_MODE, "truncated")

        self._runs[run_id] = {
            "span": span,
            "started_at": time.perf_counter(),
            "model": model,
            "provider": provider,
            "first_chunk_seen": False,
            # Operational count is unconditional. Content is separate, bounded,
            # and absent when capture is disabled.
            "chunk_count": 0,
            "captured_chunks": [] if self._capture_content else None,
            "captured_chars": 0,
            "capture_truncated": False,
            "output_type": output_type,
        }

    async def on_llm_new_token(self, token, *, run_id, chunk=None, **kwargs) -> None:
        """Fires only for a streaming model. Owns time-to-first-chunk."""
        run = self._runs.get(run_id)
        if run is None:
            return

        run["chunk_count"] += 1

        if not run["first_chunk_seen"]:
            elapsed = time.perf_counter() - run["started_at"]
            run["span"].set_attribute(GENAI_TIME_TO_FIRST_CHUNK, elapsed)
            record_time_to_first_chunk(
                elapsed,
                operation="chat",
                provider=run["provider"],
                request_model=run["model"],
            )
            run["first_chunk_seen"] = True

        if run["captured_chunks"] is not None:
            text = str(token)
            remaining = MAX_CAPTURED_OUTPUT_CHARS - run["captured_chars"]
            if remaining > 0:
                captured = text[:remaining]
                run["captured_chunks"].append(captured)
                run["captured_chars"] += len(captured)
            if len(text) > max(remaining, 0):
                run["capture_truncated"] = True

    async def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        span = run["span"]

        metadata = extract_response_metadata(response)
        if "response_model" in metadata:
            span.set_attribute(GENAI_RESPONSE_MODEL, metadata["response_model"])
        if "response_id" in metadata:
            span.set_attribute(GENAI_RESPONSE_ID, metadata["response_id"])
        if "finish_reasons" in metadata:
            span.set_attribute(GENAI_FINISH_REASONS, metadata["finish_reasons"])

        # Extracted once, used twice: the span attributes and the token
        # histogram must come from the same dict or they can drift apart.
        usage = extract_usage_metadata(response)
        set_usage_attributes(span, usage)

        if self._streaming:
            span.set_attribute(
                "app.gen_ai.stream.chunk_count", run["chunk_count"]
            )

        if self._capture_content:
            # Observed, not configured: if chunks actually arrived, the joined
            # buffer is the response. Otherwise the LLMResult is.
            if run["chunk_count"]:
                span.set_attribute(
                    GENAI_OUTPUT_MESSAGES,
                    serialize_text_output(
                        "".join(run["captured_chunks"]),
                        (metadata.get("finish_reasons") or ["unknown"])[0],
                    ),
                )
                span.set_attribute(
                    APP_OBSERVATION_OUTPUT,
                    serialize_observation_text_output(
                        "".join(run["captured_chunks"]), run["output_type"]
                    ),
                )
                if run["capture_truncated"]:
                    span.set_attribute(
                        "app.gen_ai.output.capture_mode", "truncated"
                    )
            else:
                span.set_attribute(
                    GENAI_OUTPUT_MESSAGES, serialize_llm_result(response)
                )
                span.set_attribute(
                    APP_OBSERVATION_OUTPUT,
                    serialize_observation_output(response, run["output_type"]),
                )

        record_model_operation(
            duration_s=time.perf_counter() - run["started_at"],
            operation="chat",
            provider=run["provider"],
            request_model=run["model"],
            response_model=metadata.get("response_model"),
            usage=usage,
        )
        span.end()

    async def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        span = run["span"]

        if self._streaming:
            span.set_attribute(
                "app.gen_ai.stream.chunk_count", run["chunk_count"]
            )

        # A framework callback cannot use start_span, so it marks the span
        # itself (../../../conventions/errors.md). The boundary logs the detail.
        mark_error(span, error)

        record_model_operation(
            duration_s=time.perf_counter() - run["started_at"],
            operation="chat",
            provider=run["provider"],
            request_model=run["model"],
            error_type=error_type_of(error),
        )
        span.end()
```

Four details that are not obvious:

- **`start_span`, not `start_as_current_span`.** The callback returns before the model call completes, so there is no scope to attach. The span's parent is captured at creation from the then-current context, which is the agent span.
- **`pop(run_id, None)`, always.** A run that never emits an end event must not raise a `KeyError` inside instrumentation. It leaks one span object instead — recoverable — rather than breaking the request.
- **The metric is recorded on both paths.** Recording duration only on success gives an error rate computed against a denominator that excludes errors.
- **`chunk_count` decides where captured output comes from, not the `streaming` flag.** If the flag and the model configuration ever disagree, the content still comes from whichever one actually produced text.

### Non-chat models

`on_chat_model_start` only fires for chat models. A service using a
completion-style LLM (`OpenAI(...)`, `HuggingFacePipeline`, anything LangChain
routes as an LLM rather than a ChatModel) emits `on_llm_start` instead and
produces **zero spans** with the handler above. The shape is the same; add:

```python
    async def on_llm_start(
        self, serialized, prompts, *, run_id, metadata=None, **kwargs
    ) -> None:
        # `prompts` is list[str] rather than a message list, and the operation
        # is text_completion (see ../attributes.md). Everything else — model
        # resolution, counters, span creation, run bookkeeping — is identical;
        # factor the body of on_chat_model_start into a helper both call.
        ...
```

Set `gen_ai.operation.name="text_completion"` and, when capturing content,
serialize `prompts` rather than passing them to `serialize_chat_model_input`,
whose contract is a message list.

LangChain also exposes `on_retriever_start` / `on_retriever_end`. This skill
does **not** use them: retrieval spans are written explicitly in
`../retrieval.md` because they must be identical on the direct-SDK path, where
no callback exists. Do not instrument retrieval twice.

### Span leaks

If neither `on_llm_end` nor `on_llm_error` fires — a cancelled request, a provider integration that swallows the event — the span never ends and never exports. Add a guard when the agent runs long or handles cancellation:

```python
def abandon_runs_older_than(self, max_age_s: float) -> None:
    now = time.perf_counter()
    for run_id, run in list(self._runs.items()):
        if now - run["started_at"] > max_age_s:
            run = self._runs.pop(run_id, None)
            if run:
                run["span"].set_status(Status(StatusCode.ERROR))
                # Documented sentinel, not a class name: no exception occurred.
                # The closed set is in ../../../conventions/errors.md.
                run["span"].set_attribute(ERROR_TYPE, "_ABANDONED")
                if self._streaming:
                    run["span"].set_attribute(
                        "app.gen_ai.stream.chunk_count", run["chunk_count"]
                    )
                record_model_operation(
                    duration_s=now - run["started_at"],
                    operation="chat",
                    provider=run["provider"],
                    request_model=run["model"],
                    error_type="_ABANDONED",
                )
                run["span"].end()
```

Call it from the outer agent wrapper's `finally`. A growing `self._runs` in a long-lived process is a memory leak as well as missing telemetry.

---

## Streaming

Streaming adds one thing that matters: **time to first chunk**, the latency the
user actually perceives. It comes from `on_llm_new_token`, which fires on the
real token stream — not from agent-level stream updates, which are step-granular
and arrive much later. The `on_llm_new_token` hook above owns it; the additional
imports it needs are `GENAI_TIME_TO_FIRST_CHUNK` and
`record_time_to_first_chunk`, already listed in the fence.

### Streaming token usage is opt-in at the model

```python
streaming_model = init_chat_model(
    "openai:gpt-5",
    streaming=True,
    # Without this, on_llm_end receives no usage_metadata for streamed calls.
    stream_usage=True,
).with_config(callbacks=[OTelModelCallback(capture_content=capture_ai_content, streaming=True)])
```

Miss it and the spans look correct but usage attributes and observations are absent. Why, and the equivalent for other providers: `../token_usage.md`.

### Chunk count and captured content

`chunk_count` increments on every chunk whether capture is on or off. The
content list exists only when capture is enabled and is capped at 32 KiB; a
larger response sets `app.gen_ai.output.capture_mode="truncated"`. This keeps
operational telemetry correct without buffering production responses when the
safe default is active.

---

## How to attach it

Use the flags and sync/async verification in `provider_compatibility.md`; they are
properties of the physical adapter and production invocation style.

---

## Verify before moving on

Run one agent invocation and check the exported spans:

- one `chat <model>` span per model call — including the summarization call, if configured;
- the model name is the **real** one, and differs between the main and summarization models; when unavailable, `gen_ai.request.model` is absent and never `chat` or `llm`;
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` are non-zero;
- `gen_ai.usage.cache_read.input_tokens` is present, even if `0`;
- with streaming, `gen_ai.response.time_to_first_chunk` is set and is smaller than the span duration;
- `app.gen_ai.stream.chunk_count` is correct with capture both on and off, including an error after the first chunk;
- the agent is invoked **the way production invokes it** (sync or async) and model spans still appear;
- `gen_ai.response.model` appears on the span and the model-duration/token metrics when the provider returns it;
- when the provider returns a finish reason, both `gen_ai.response.finish_reasons` and each captured output message preserve it instead of falling back to `unknown`;
- native structured output emits `gen_ai.output.type=json`, while its JSON text remains inside the standard output-message envelope;
- text-only observation input renders as role/content and one valid JSON response renders as
  the decoded object, while multipart output falls back to the canonical envelope;
- a provider with a separate system field emits `gen_ai.system_instructions` without a duplicate system-role input message, while provider-reported usage stays unchanged;
- representative non-text provider content blocks survive serialization instead of becoming empty text;
- forcing a provider error produces a span with `ERROR` status and `error.type`, and no exception span event;
- with `CAPTURE_AI_CONTENT` unset, no `gen_ai.input.messages` attribute exists anywhere.

If the repository has tests, cover capture on/off, an empty stream,
cancellation, an error after the first chunk, and the abandoned-run guard.

Then continue to `tools_and_middleware.md`.
