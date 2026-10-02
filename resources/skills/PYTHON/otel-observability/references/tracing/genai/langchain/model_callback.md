# LangChain Model Callback

One span per **physical** model request, with model identity, parameters, token usage, and — when streaming — time to first chunk.

The callback fires below every middleware, so retries produce separate spans with no retry-specific code (`architecture.md`, "Why the callback, specifically, for models").

Two neighbours own what it writes: token counts come from `../token_usage.md`, prompt and completion capture from `../content_capture.md`.

## Contents

- [Compatibility gate](#compatibility-gate)
- [Model and provider identity](#resolving-model-identity)
- [`LLMResult` metadata](#reading-the-llmresult)
- [The callback](#the-callback)
- [Streaming](#streaming)
- [How to attach it](#how-to-attach-it)
- [Verification](#verify-before-moving-on)

The callback itself is `assets/langchain/model_callback.py` (skill root). The fences
below are the helpers it imports or expects beside it; `extract_usage_metadata()` comes
from `../token_usage.md` and the serializers from `../content_capture.md`.

For provider- and version-specific message or metadata shapes, first complete the
[compatibility gate](#compatibility-gate).

## Compatibility gate

Read this when adding or changing a model provider, provider adapter, LangChain,
LangGraph, or a backend that renders captured LLM input/output. Provider
serialization is a versioned adapter contract, not a naming convention.

Before implementing or repairing a callback:

1. Read the repository lockfile and identify the exact framework and provider-adapter
   versions used in production.
2. Inspect the installed adapter's request conversion and response parsing source.
   Confirm whether system instructions leave the message list, how structured output
   is requested, which content blocks reach `AIMessage`, and the exact response metadata
   keys. If local source does not settle the contract, search current **official**
   framework and provider documentation; do not rely on blogs or remembered casing.
3. Capture one bounded representative callback start/end payload and the raw exported
   span attributes. Inspect those raw values before interpreting how Langfuse or another
   backend renders them. Then inspect the backend's stored observation input/output: an
   expandable `parts[0]` object can contain the output even when the collapsed UI says only
   `2 items`, while a correct raw attribute can still fail backend ingestion mapping.
4. Add a hermetic provider fixture containing the observed shapes. Assert system-field
   ownership, decoded input/output message JSON, structured-output type, finish reason,
   model identity, usage, preservation of relevant non-text content blocks, and any
   destination presentation projection. For a JSON response, assert both the canonical
   text part and the decoded observation object.
5. Keep a marked live provider check for capability drift when its credentials and cost
   are justified. A unit fixture proves one recorded adapter shape, not current provider
   behaviour.

Normalize only the stable OpenTelemetry envelope (`role`, `parts`,
`finish_reason`). Do not flatten every provider part to text, assume one metadata
casing, or treat a backend's expandable JSON rendering as raw wire evidence. See
`../content_capture.md`, "Backend rendering is not the wire shape". The rules for a
backend-native presentation projection (`app.gen_ai.observation.*`, including an empty
`reasoning` part next to one text part) are in `../../../backends/langfuse.md`,
"Observation input and output".

For example, the reviewed `langchain-aws` Bedrock Converse adapter sends
`SystemMessage` content through Bedrock's top-level `system` field and preserves the
provider's camel-case `stopReason` in response metadata. Generic code that keeps the
system message in chat history or reads only `stop_reason` produces plausible but
false telemetry.

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

The complete module is `assets/langchain/model_callback.py` (skill root). Copy it into
the service's `observability/` package rather than retyping it, then adapt the imports:
`observability.genai_attributes`, `genai_content`, `genai_usage`, `metrics`, `spans`, and
`agent_counters` are the modules the rest of `tracing/genai/` defines. Read it before
changing it; the sections below explain the decisions it encodes.

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

If neither `on_llm_end` nor `on_llm_error` fires — a cancelled request, a provider integration that swallows the event — the span never ends and never exports. Add a guard when the agent runs long or handles cancellation.

The guard is `abandon_runs_older_than()` at the end of the template. It ends each
stale run with `ERROR` status, `error.type="_ABANDONED"` (a documented sentinel from
`../../../conventions/errors.md`, not a class name), its chunk count when streaming, and
the same `record_model_operation` observation as the other exit paths.

Call it from the outer agent wrapper's `finally`. A growing `self._runs` in a long-lived process is a memory leak as well as missing telemetry.

---

## Streaming

Streaming adds one thing that matters: **time to first chunk**, the latency the
user actually perceives. It comes from `on_llm_new_token`, which fires on the
real token stream — not from agent-level stream updates, which are step-granular
and arrive much later. The `on_llm_new_token` hook in the template
(`assets/langchain/model_callback.py`, skill root; not reproduced in this file) owns
it; the additional imports it needs are `GENAI_TIME_TO_FIRST_CHUNK` and
`record_time_to_first_chunk`, already imported by the template.

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

`chunk_count` increments on every chunk whether capture is on or off, and is
written as `app.gen_ai.stream.chunk_count` (`APP_STREAM_CHUNK_COUNT`). The
content list exists only when capture is enabled and is capped at 32 KiB; a
larger response sets `app.gen_ai.output.capture_mode="truncated"`
(`APP_OUTPUT_CAPTURE_MODE`, `../content_capture.md`). This keeps
operational telemetry correct without buffering production responses when the
safe default is active.

---

## How to attach it

The flags and the sync/async check below are properties of the physical adapter and
the production invocation style.

### Attach configuration to the physical adapter

| Situation | Attach |
| --- | --- |
| Non-streaming model | `OTelModelCallback(capture_content=...)` |
| Streaming model | `OTelModelCallback(capture_content=..., streaming=True)` |
| Adapter with a separate system field, such as Bedrock Converse | `OTelModelCallback(capture_content=..., separate_system_instructions=True)` |
| Both in one service | Use one instance per model with matching flags; instances may be shared only by models with the same wire contract |
| Completion-style non-chat LLM | Add `on_llm_start` as described in [Non-chat models](#non-chat-models) |

**One instance per wire contract.** Run state is keyed by `run_id`, so concurrent
calls never collide and one instance can serve every model whose flags match — a
main model and its summarization model, for example. A model with a different
`streaming` or `separate_system_instructions` value needs its own instance. Build
each instance in bootstrap from the settings slice.

Choose `separate_system_instructions` from the adapter's wire contract, not merely
because the framework object is named `SystemMessage`. The projection never changes
token usage (`../token_usage.md`, "The mapping rule").

Attach the callback to the **model** (`with_config(callbacks=[...])`), not only to the
invocation config. A callback passed at invoke time still reaches model calls, but
attaching it to the model means every path that uses that model — including
middleware-owned paths — is instrumented without the caller remembering. The complete
wiring is in `tools_and_middleware.md`, "Complete middleware stack".

### Sync versus async invocation

Whether an `AsyncCallbackHandler` also covers synchronous `invoke()` or `stream()`
depends on the pinned `langchain-core`. Resolve it once using the exact production
invocation style:

1. Call the agent exactly as production does.
2. Confirm that a `chat <model>` span exports.
3. If none appears, attach a `BaseCallbackHandler` with equivalent synchronous methods
   and record that both implementations are required.

Never verify with `ainvoke` and ship `invoke`. Instrumentation often fails silently,
so a missing callback invocation otherwise looks like a healthy quiet service.

---

## Verify before moving on

Run one agent invocation and check the exported spans:

- one `chat <model>` span per model call — including the summarization call, if configured;
- the model name is the **real** one, and differs between the main and summarization models; when unavailable, `gen_ai.request.model` is absent and never `chat` or `llm`;
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` are non-zero;
- `gen_ai.usage.cache_read.input_tokens` is present when the provider reports it, including an explicit `0`, and absent when unavailable (`../token_usage.md`, "Verify");
- with streaming, `gen_ai.response.time_to_first_chunk` is set and is smaller than the span duration;
- `app.gen_ai.stream.chunk_count` is correct with capture both on and off, including an error after the first chunk;
- the agent is invoked **the way production invokes it** (sync or async) and model spans still appear;
- `gen_ai.response.model` appears on the span and the model-duration/token metrics when the provider returns it;
- when the provider returns a finish reason, both `gen_ai.response.finish_reasons` and each captured output message preserve it instead of falling back to `unknown`;
- native structured output emits `gen_ai.output.type=json`, while its JSON text remains inside the standard output-message envelope;
- when the backend projection is in use, its observation checks pass (`../../../backends/langfuse.md`, "Verify");
- a provider with a separate system field emits `gen_ai.system_instructions` without a duplicate system-role input message;
- representative non-text provider content blocks survive serialization instead of becoming empty text;
- forcing a provider error produces a span with `ERROR` status and `error.type`, and no exception span event;
- with `CAPTURE_AI_CONTENT` unset, no `gen_ai.input.messages` attribute exists anywhere.

If the repository has tests, cover capture on/off, an empty stream,
cancellation, an error after the first chunk, and the abandoned-run guard.

Then continue to `tools_and_middleware.md`.
