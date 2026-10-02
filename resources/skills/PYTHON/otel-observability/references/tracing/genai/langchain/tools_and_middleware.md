# Tool Spans, Retry Middleware, and Summarization

Tools are where agents actually fail. A tool span must represent the **execution**, not the model's decision to call one.

Tool arguments and results are opt-in content on the same switch as prompts — `../content_capture.md`.

---

## The tool tracing middleware

```python
# observability/genai.py
import time
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from observability.agent_counters import current_counters
from observability.genai_attributes import (
    APP_TOOL_REQUESTED_NAME,
    APP_TOOL_RESULT_SIZE_BYTES,
    GENAI_OPERATION_NAME,
    GENAI_TOOL_CALL_ARGUMENTS,
    GENAI_TOOL_CALL_ID,
    GENAI_TOOL_CALL_RESULT,
    GENAI_TOOL_NAME,
    GENAI_TOOL_TYPE,
)
from observability.genai_content import serialize_tool_input, serialize_tool_output
from observability.metrics import record_tool_execution
from observability.spans import error_type_of, start_span

# Tool names come from the model and are therefore untrusted input.
# Anything outside this set is bucketed before it reaches a span name or a
# metric attribute.
KNOWN_TOOLS = {"web_search", "order_lookup", "account_lookup"}


def normalize_tool_name(name: str) -> str:
    return name if name in KNOWN_TOOLS else "unknown_tool"


def build_trace_tool_call(*, capture_content: bool) -> AgentMiddleware:
    """Build the tool tracing middleware.

    Bootstrap passes the settings value, like OTelModelCallback(capture_content=...);
    nothing reads settings or a module global at import or call time.
    """

    @wrap_tool_call
    async def trace_tool_call(
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        raw_name = request.tool_call["name"]
        tool_name = normalize_tool_name(raw_name)
        started_at = time.perf_counter()
        error_type: str | None = None

        # Retry middleware invokes this wrapper once per physical attempt, so this
        # increments the same unit represented by each tool span.
        counters = current_counters()
        if counters is not None:
            counters.tool_calls += 1

        try:
            with start_span(
                f"execute_tool {tool_name}",
                attributes={
                    GENAI_OPERATION_NAME: "execute_tool",
                    GENAI_TOOL_NAME: tool_name,
                    GENAI_TOOL_TYPE: "function",
                },
            ) as span:
                if tool_call_id := request.tool_call.get("id"):
                    span.set_attribute(GENAI_TOOL_CALL_ID, tool_call_id)
                if tool_name != raw_name:
                    # Keep the real name findable without letting it into the
                    # span name.
                    span.set_attribute(APP_TOOL_REQUESTED_NAME, raw_name[:128])

                if capture_content:
                    span.set_attribute(
                        GENAI_TOOL_CALL_ARGUMENTS,
                        serialize_tool_input(request.tool_call.get("args", {})),
                    )

                response = await handler(request)

                if capture_content:
                    span.set_attribute(
                        GENAI_TOOL_CALL_RESULT, serialize_tool_output(response)
                    )
                else:
                    # Cheap and safe: size spots context blow-ups without
                    # capturing content.
                    span.set_attribute(
                        APP_TOOL_RESULT_SIZE_BYTES, len(str(response).encode())
                    )

                return response
        except BaseException as exc:
            # start_span marked the span; this only labels the metric.
            error_type = error_type_of(exc)
            raise
        finally:
            # Outside the span, and on both paths: recording only on success gives
            # a tool error rate whose denominator excludes errors.
            record_tool_execution(
                duration_s=time.perf_counter() - started_at,
                tool_name=tool_name,
                error_type=error_type,
            )

    return trace_tool_call
```

Bootstrap builds it once, `trace_tool_call = build_trace_tool_call(capture_content=settings.capture_ai_content)`, and passes `trace_tool_call` to `create_agent` ("Complete middleware stack" below). The async decorator is `@wrap_tool_call` applied to an `async def`; the class-based equivalent is `awrap_tool_call`. Use the async form when the agent is invoked with `ainvoke`/`astream`.

`ToolCallRequest` gives you `request.tool_call` (a dict with `name`, `args`, `id`), plus `request.state` and `request.runtime` if you need agent state for a business attribute.

---

## Middleware ordering decides what a tool span means

Both `ToolRetryMiddleware` and your tracing middleware operate at the middleware layer, so their relative order is the whole design decision.

**In `create_agent(middleware=[...])`, earlier entries are outermost.** The first middleware wraps all the others.

### Ordering A — tracing outside retries

```python
middleware=[
    trace_tool_call,
    ToolRetryMiddleware(max_retries=2, retry_on=(TimeoutError, ConnectionError)),
]
```

```
trace_tool_call
└── ToolRetryMiddleware
      ├── tool attempt #1  ✗
      ├── tool attempt #2  ✗
      └── tool attempt #3  ✓
```

Result: **one** span covering the complete logical tool call.

```
execute_tool web_search    OK    duration=7.0s
```

You lose the attempts entirely. A tool that eventually succeeds hides a real operational problem: two timeouts and seven seconds of user-visible latency look identical to one healthy 7-second call.

### Ordering B — retries outside tracing (prefer this)

```python
middleware=[
    ToolRetryMiddleware(max_retries=2, retry_on=(TimeoutError, ConnectionError)),
    trace_tool_call,
]
```

```
ToolRetryMiddleware
├── trace_tool_call → tool attempt #1  ✗
├── trace_tool_call → tool attempt #2  ✗
└── trace_tool_call → tool attempt #3  ✓
```

Result: **one span per physical attempt**.

```
invoke_agent support_agent
├── execute_tool web_search   ERROR   TimeoutError      3.0s
├── execute_tool web_search   ERROR   ConnectionError   3.0s
└── execute_tool web_search   OK                        1.0s
```

Now the trace states the operational fact: the tool failed twice and cost six wasted seconds. That is what you need in an incident, and it is what tool error-rate metrics should be counting.

Prefer physical-attempt tracing. If you also want the logical call's total latency in one place, add a thin outer span rather than giving up per-attempt visibility.

### Models are different — no ordering decision needed

For models the callback sits **below** the retry middleware, so each retry is a separate physical request with its own span and `ModelRetryMiddleware` needs no tracing-specific configuration. Diagram: `architecture.md`, "Why the callback, specifically, for models".

---

## Do not retry everything

`ToolRetryMiddleware` defaults to `default_retry_on`: it retries all
unclassified exceptions and retries a LangChain `ModelError` only when that
error marks itself retryable. That broad fallback is almost never the right
policy for production tools.

Retry **transient, system-recoverable** failures:

```
timeouts
temporary network failures
rate limits
temporary provider failures (5xx)
```

Do **not** retry failures the model can fix:

```
invalid arguments
schema/validation errors
"not found" for a value the model invented
business-rule rejections
```

Those should go back to the model as a tool result so the agent can correct its call. Retrying the identical invalid call three times produces three identical failures, triples latency and cost, and buries the actual defect under retry noise.

```python
ToolRetryMiddleware(
    max_retries=2,
    retry_on=(TimeoutError, ConnectionError),   # explicit, not the default
    on_failure="continue",                      # surface the error to the model
)
```

`on_failure="continue"` returns an error message to the model; `"error"` re-raises and ends the run. Choose deliberately — it changes both agent behaviour and what the trace shows.

Scope retries to specific tools with `tools=[...]` when only some are worth retrying — a read-only search, yes; a write operation, only with an idempotency key.

---

## Summarization model

`SummarizationMiddleware` can use a different, usually cheaper, model. Attach the **same** callback to it so its calls appear as ordinary model spans instead of vanishing into the middleware (sharing one instance is safe while the flags match: `model_callback.md`, "How to attach it").

```python
from langchain.agents.middleware import SummarizationMiddleware

summary_model = init_chat_model("openai:gpt-5-mini", streaming=False).with_config(
    callbacks=[otel_model_callback],
)

summarization = SummarizationMiddleware(
    model=summary_model,
    trigger=("tokens", 100_000),
    keep=("messages", 20),
)
```

```
main agent LLM   ──> OTelModelCallback
summarization LLM ─> OTelModelCallback
```

Without the callback on the summarization model, those calls are invisible: their latency and tokens land nowhere, and the agent's total cost silently under-reports. Since the model name is resolved per call (`model_callback.md`), the summarization span is distinguishable by `gen_ai.request.model` without any extra wiring.

Summarization frequency is worth watching. A jump in summarization calls per invocation means context is growing — usually a prompt or retrieval regression. See `../../../metrics/genai.md`.

Whether the model call after summarization sets `gen_ai.conversation.compacted=true`: `../attributes.md`, "Conversation correlation".

---

## Complete middleware stack

This file owns the wiring; `architecture.md` links here.

```python
# agents/support_agent.py
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware, ToolRetryMiddleware
from langchain.chat_models import init_chat_model

from observability.genai import OTelModelCallback, build_trace_tool_call

# Built in bootstrap from the settings slice. One callback instance serves both
# models because their flags match (model_callback.md, "How to attach it").
otel_model_callback = OTelModelCallback(capture_content=settings.capture_ai_content)
trace_tool_call = build_trace_tool_call(capture_content=settings.capture_ai_content)

main_model = init_chat_model("openai:gpt-5", streaming=False).with_config(
    callbacks=[otel_model_callback],
)
# summary_model and `summarization`: "Summarization model" above, with the
# SAME callback attached to summary_model.

agent = create_agent(
    model=main_model,
    tools=tools,
    middleware=[
        # Order matters. Earlier = outer.
        # Retries physical model calls. The callback below the model traces
        # every physical attempt, so nothing extra is needed here.
        ModelRetryMiddleware(max_retries=2),

        # Outside tool tracing, so each attempt gets its own span.
        ToolRetryMiddleware(
            max_retries=2,
            retry_on=(TimeoutError, ConnectionError),
        ),

        # Inside the retry wrapper: runs once per physical tool attempt.
        trace_tool_call,

        summarization,
    ],
)
```

Resulting trace:

```
invoke_agent support_agent
├── chat gpt-5                 OK
├── execute_tool web_search    ERROR  TimeoutError
├── execute_tool web_search    ERROR  ConnectionError
├── execute_tool web_search    OK
├── chat gpt-5-mini            OK      (summarization)
└── chat gpt-5                 OK
```

---

## Verify before moving on

- One `execute_tool <name>` span per **attempt**, not per logical call — force a transient failure to check.
- Failed attempts have `ERROR` status and a bounded `error.type`.
- Tool spans are children of the agent span, not siblings.
- An unknown tool name produces `execute_tool unknown_tool`, with the raw name only in `app.gen_ai.tool.requested_name`.
- With `CAPTURE_AI_CONTENT` unset (`build_trace_tool_call(capture_content=False)`), no `gen_ai.tool.call.arguments` or `gen_ai.tool.call.result` appears.
- The summarization model produces its own span with its own model name.

Then continue to `streaming_and_agent_span.md`.
