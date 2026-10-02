# Direct Provider SDK Instrumentation

For services that call OpenAI, Anthropic, Bedrock, Azure OpenAI, or Google GenAI/Vertex directly, without an agent framework. This is usually the simpler case: standalone model calls rather than an agent loop.

Three neighbours own what this file uses: `attributes.md` (the constants module), `token_usage.md` (`set_usage_attributes` and the per-provider adapters), and `content_capture.md` (the `CAPTURE_AI_CONTENT` switch). Read `attributes.md` first.

## Contents

- [Provider wrapper](#one-wrapper-per-provider-not-a-span-at-every-call-site)
- [Usage adapters](#usage)
- [Streaming](#streaming)
- [Retries](#application-level-retries)
- [Checklist](#checklist)

The provider wrappers are **partial integration templates** because the SDK
client and response adapter are service dependencies. Before copying one, add
the exact adapter from `token_usage.md`; the streaming fragment additionally
requires local `extract_stream_usage()` and `extract_text_delta()` helpers for
the locked provider SDK. Do not treat an undefined helper as pseudocode that is
safe to deploy.

---

## One wrapper per provider, not a span at every call site

Put the span, the attribute mapping, and the provider-specific response parsing in one function. Everything else in the service calls that function.

Why: response shapes differ per provider and change between SDK versions. If forty call sites each read `response.usage.prompt_tokens`, an SDK upgrade is a forty-site migration and the attributes drift apart in the meantime.

```python
# llm/openai_client.py
import time
from collections.abc import Iterator, Sequence

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from observability.genai_attributes import (
    APP_OUTPUT_CAPTURE_MODE,
    APP_STREAM_CHUNK_COUNT,
    GENAI_FINISH_REASONS,
    GENAI_INPUT_MESSAGES,
    GENAI_OPERATION_NAME,
    GENAI_OUTPUT_MESSAGES,
    GENAI_OUTPUT_TYPE,
    GENAI_PROVIDER_NAME,
    GENAI_REQUEST_MAX_TOKENS,
    GENAI_REQUEST_MODEL,
    GENAI_REQUEST_STREAM,
    GENAI_REQUEST_TEMPERATURE,
    GENAI_RESPONSE_ID,
    GENAI_RESPONSE_MODEL,
    GENAI_TIME_TO_FIRST_CHUNK,
)
from observability.genai_content import serialize_messages, serialize_text_output
from observability.metrics import (
    record_model_operation,
    record_time_to_first_chunk,
)
from observability.genai_usage import set_usage_attributes
from observability.spans import error_type_of, mark_error, start_span

tracer = trace.get_tracer(__name__)


def complete_chat(
    client: OpenAI,
    messages: Sequence[ChatCompletionMessageParam],
    *,
    model: str,
    capture_ai_content: bool,  # from settings, passed down by bootstrap
    temperature: float = 0.2,
    max_tokens: int = 800,
) -> str:
    with start_span(
        # Low-cardinality: operation plus model, never the prompt.
        f"chat {model}",
        kind=SpanKind.CLIENT,
        # Set at creation time so a sampler can act on them.
        attributes={
            GENAI_OPERATION_NAME: "chat",
            GENAI_PROVIDER_NAME: "openai",
            GENAI_REQUEST_MODEL: model,
            GENAI_REQUEST_STREAM: False,
            GENAI_OUTPUT_TYPE: "text",
            GENAI_REQUEST_TEMPERATURE: temperature,
            GENAI_REQUEST_MAX_TOKENS: max_tokens,
        },
    ) as span:
        started = time.perf_counter()
        error_type: str | None = None
        usage: dict[str, object] | None = None
        response_model: str | None = None

        if capture_ai_content:
            span.set_attribute(GENAI_INPUT_MESSAGES, serialize_messages(messages))

        try:
            response = client.chat.completions.create(
                model=model,
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Extracted inside the try so the finally below can record token
            # metrics as well as duration. On the error path it stays None and
            # only the duration observation is recorded.
            usage = extract_usage(response)
            response_model = getattr(response, "model", None)
        except BaseException as exc:
            # start_span marks the span; this only labels the metric.
            error_type = error_type_of(exc)
            raise
        finally:
            # Duration must be recorded on both paths, or the error rate is
            # computed against a denominator that excludes failures.
            record_model_operation(
                duration_s=time.perf_counter() - started,
                operation="chat",
                provider="openai",
                request_model=model,
                response_model=response_model,
                usage=usage,
                error_type=error_type,
            )

        choice = response.choices[0]
        answer = choice.message.content or ""
        finish_reason = choice.finish_reason or "unknown"

        if response_model:
            span.set_attribute(GENAI_RESPONSE_MODEL, response_model)
        span.set_attribute(GENAI_RESPONSE_ID, response.id)
        span.set_attribute(GENAI_FINISH_REASONS, [finish_reason])

        # Same dict the metric got, so span and histogram cannot disagree.
        set_usage_attributes(span, usage)

        if capture_ai_content:
            span.set_attribute(
                GENAI_OUTPUT_MESSAGES,
                serialize_text_output(answer, finish_reason),
            )

        return answer
```

Span kind is `CLIENT` for a remote provider and `INTERNAL` for an in-process model.

The span covers **one logical operation**. If the SDK retries internally, the span covers all of it — that is what the caller experienced. Retries the *application* performs are separate spans; see below.

---

## Usage

`extract_usage()` above is intentionally not defined in this fragment. It is the provider adapter that converts this SDK's response shape into the normalized usage dict, which `set_usage_attributes()` then writes. Copy the complete adapter for the locked SDK from **`token_usage.md`**, keep it next to this wrapper in code, and add an import/compile smoke test so a renamed SDK field fails in CI rather than production.

For Bedrock specifically: read usage from the `bedrock-runtime` response body, and note that `opentelemetry-instrumentation-botocore` is deliberately **not** installed (see `../../setup/auto_instrumentation.md`) — it would trace every low-level AWS call. Instrument the model call by hand as above.

---

## Streaming

Two different latencies matter: time to the first chunk (what the user perceives) and total duration (the span). Record both.

**Never hold a current span across a `yield`** — not `start_as_current_span`,
and not the shared `start_span` helper, which wraps it. Create the span with the
manual `tracer.start_span()` and end it in `finally`; the reason is in
[Why the span is never current across a `yield`](#why-the-span-is-never-current-across-a-yield).

```python
def stream_chat(
    client: OpenAI,
    messages: Sequence[ChatCompletionMessageParam],
    *,
    model: str,
    capture_ai_content: bool,
) -> Iterator[str]:
    # The manual tracer.start_span(), not the start_span helper (it makes the
    # span current, which must not happen across a yield — see below the fence).
    # The parent is whatever span is current at the FIRST iteration, because a
    # generator body does not run until then.
    span = tracer.start_span(
        f"chat {model}",
        kind=SpanKind.CLIENT,
        attributes={
            GENAI_OPERATION_NAME: "chat",
            GENAI_PROVIDER_NAME: "openai",
            GENAI_REQUEST_MODEL: model,
            GENAI_REQUEST_STREAM: True,
        },
    )
    started = time.perf_counter()
    first_chunk_at: float | None = None
    chunk_count = 0
    captured_chunks: list[str] | None = (
        [] if capture_ai_content else None
    )
    captured_chars = 0
    capture_truncated = False
    error_type: str | None = None
    usage: dict[str, object] | None = None
    response_model: str | None = None
    response_id: str | None = None
    finish_reason: str | None = None

    try:
        # Only the non-yielding work is made current, so any span the SDK or a
        # retry hook creates still nests under the model span.
        with trace.use_span(span, end_on_exit=False, record_exception=False):
            stream = client.chat.completions.create(
                model=model,
                messages=list(messages),
                stream=True,
                # Without this, the final usage chunk is never sent and token
                # counts are silently missing for every streamed call.
                stream_options={"include_usage": True},
            )

        for chunk in stream:
            chunk_count += 1
            if first_chunk_at is None:
                first_chunk_at = time.perf_counter()
                span.set_attribute(
                    GENAI_TIME_TO_FIRST_CHUNK, first_chunk_at - started
                )
                record_time_to_first_chunk(
                    first_chunk_at - started,
                    operation="chat",
                    provider="openai",
                    request_model=model,
                )

            response_model = getattr(chunk, "model", None) or response_model
            response_id = getattr(chunk, "id", None) or response_id
            if response_model:
                span.set_attribute(GENAI_RESPONSE_MODEL, response_model)
            if response_id:
                span.set_attribute(GENAI_RESPONSE_ID, response_id)
            for choice in getattr(chunk, "choices", None) or []:
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                    span.set_attribute(GENAI_FINISH_REASONS, [finish_reason])
                    break

            # Arrives on a final chunk whose `choices` list is empty.
            if chunk.usage is not None:
                usage = extract_stream_usage(chunk)
                set_usage_attributes(span, usage)

            text = extract_text_delta(chunk)
            if text:
                if captured_chunks is not None:
                    remaining = 32_768 - captured_chars
                    if remaining > 0:
                        captured = text[:remaining]
                        captured_chunks.append(captured)
                        captured_chars += len(captured)
                    if len(text) > max(remaining, 0):
                        capture_truncated = True
                yield text
    except BaseException as exc:
        # A manual span: a context manager cannot be held across `yield`.
        # GeneratorExit (an abandoned stream) is a real, bounded class name.
        error_type = error_type_of(exc)
        mark_error(span, exc)
        raise
    finally:
        # `usage` is None if the stream errored before the final chunk, or
        # if include_usage was not requested — the duration observation is
        # still recorded either way.
        span.set_attribute(APP_STREAM_CHUNK_COUNT, chunk_count)
        if captured_chunks is not None:
            span.set_attribute(
                GENAI_OUTPUT_MESSAGES,
                serialize_text_output(
                    "".join(captured_chunks),
                    finish_reason or ("error" if error_type else "unknown"),
                ),
            )
            if error_type:
                span.set_attribute(APP_OUTPUT_CAPTURE_MODE, "partial")
            elif capture_truncated:
                span.set_attribute(APP_OUTPUT_CAPTURE_MODE, "truncated")
        record_model_operation(
            duration_s=time.perf_counter() - started,
            operation="chat",
            provider="openai",
            request_model=model,
            response_model=response_model,
            usage=usage,
            error_type=error_type,
        )
        # tracer.start_span() has no context manager, so the end is explicit.
        span.end()
```

### Why the span is never current across a `yield`

This section owns the rule for every streaming wrapper in this skill (the
agent-level wrappers in `langchain/streaming_and_agent_span.md` and the HTTP
streaming endpoint in `../http_service.md` link here). A Python generator does
not get its own `contextvars` context: PEP 550 was rejected, so generators and
async generators share the caller's `contextvars` context.
`start_as_current_span` calls `context.attach()` on entry and detaches on exit;
between them the generator yields control **with the attach still live**,
which produces three silent defects:

- a span the consumer creates between two chunks becomes a child of the *model*
  span instead of the request span — the same "siblings where you expected
  nesting" symptom this skill elsewhere attributes to *lost* context, so the
  diagnostic points the wrong way;
- two interleaved streams unwind their `detach()` tokens out of order and the
  SDK logs `Failed to detach context`;
- concurrent streaming requests in one task can inherit each other's parent.

`tracer.start_span()` + explicit `end()` avoids all three. When a child
genuinely must nest under the model span, wrap only that work in
`trace.use_span(span, end_on_exit=False, record_exception=False)` and make sure
no `yield` sits inside it. A wrapper whose children are created *while the
generator is resumed* (an agent stream) brackets each resumption that way:
`langchain/streaming_and_agent_span.md`, `agent_step`.

### The generator must always finish

The failure mode specific to streaming *generators* is that **the span never
ends**. The span ends in the generator's `finally`, which only runs when the
generator is exhausted, closed, or garbage-collected. If a client disconnects
mid-stream and the caller abandons the generator, the span can stay open
indefinitely (until the process exits).

Guard at the caller so the generator is always exhausted or explicitly closed.
For FastAPI, `StreamingResponse` closes the generator on disconnect, but confirm
on a real client-disconnect test that the span ends. If a streaming span is
missing from a trace whose child spans are present, this is the cause.

### Helpers this fragment expects

Three provider-specific helpers must be defined or imported in the final
module. Their contracts, so the gap is a fill-in rather than a design task:

| Helper | Signature | Returns |
| --- | --- | --- |
| `extract_usage(response)` | `(Any) -> dict` | the normalized usage dict for a non-streaming response — adapter in `token_usage.md` |
| `extract_stream_usage(chunk)` | `(Any) -> dict` | the same normalized dict, read from the provider's usage-carrying chunk |
| `extract_text_delta(chunk)` | `(Any) -> str \| None` | the incremental text of this chunk; `None` for a usage-only, role-only, or tool-call-only chunk |

The constants and metric recorders it uses are imported in the first fragment.

`stream_options={"include_usage": True}` is not optional — without it the provider sends no token counts at all and the omission is silent. Why, and the equivalent for other providers: `token_usage.md`.

The generator must always finish — [rule above](#the-generator-must-always-finish).

Never create a span per token or per chunk. One span per inference call. Thousands of spans per request overwhelm the Collector and make the trace unreadable.

---

## Application-level retries

If the application retries around the SDK, each attempt should be its own span so you can see that three attempts happened rather than one slow call.

```python
for attempt in range(1, max_attempts + 1):
    try:
        return complete_chat(                                 # own span per attempt
            client, messages, model=model, capture_ai_content=capture_ai_content
        )
    except RateLimitError:
        if attempt == max_attempts:
            raise
        time.sleep(backoff(attempt))
```

Put the attempt number on the span if the wrapper accepts it (`app.gen_ai.request.attempt`), and wrap the whole retry loop in a parent span when the caller needs the total latency in one place.

Retry only transient failures — timeouts, connection errors, rate limits, 5xx. A malformed request retried three times is three identical failures and three times the cost.

---

## Checklist

- [ ] One wrapper per provider owns the span and the response parsing.
- [ ] `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model` set at span creation.
- [ ] Response model, response ID, and finish reasons recorded.
- [ ] Response model is also passed to `record_model_operation`; request and response model remain separate.
- [ ] Usage adapted from the provider's shape and passed through `set_usage_attributes()` — `token_usage.md`.
- [ ] Streaming calls request usage explicitly and record `gen_ai.response.time_to_first_chunk`.
- [ ] Streaming chunk count is correct with capture off; captured content is bounded and exists only with capture on.
- [ ] Content capture gated on `CAPTURE_AI_CONTENT`, off by default — `content_capture.md`.
- [ ] `error.type` on failure, no `record_exception`, per `../../conventions/errors.md`.
- [ ] Duration and token metrics recorded on both success and failure paths — `../../metrics/genai.md`.
- [ ] Streaming wrappers use `tracer.start_span()` + `finally: span.end()`; no span is current across a `yield`, and the generator always finishes.
- [ ] Embeddings and retrieval are their own spans — `retrieval.md`.

---

## Then

- RAG spans: `retrieval.md`
- metrics: `../../metrics/genai.md`
- logging: the `python-logging` skill (`../../../../python-logging/references/genai.md`)
