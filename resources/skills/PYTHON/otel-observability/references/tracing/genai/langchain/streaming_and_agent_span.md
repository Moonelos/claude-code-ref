# The Agent Span, Streaming, and Conversation Correlation

The outer span is the unit everything else hangs off. Nothing in LangChain emits it, so you write it.

---

## Why it has to exist

Without it, model and tool spans attach directly to the HTTP or worker span. You then have no span whose duration is "one agent invocation," which means no `gen_ai.invoke_agent.duration`, no model-calls-per-invocation, no tool-calls-per-invocation — the three signals that detect an agent regressing into a loop.

```
POST /chat                          SERVER
  invoke_agent support_agent        <- this one
    chat gpt-5
    execute_tool web_search
    chat gpt-5
```

---

## Non-streaming

```python
# observability/genai.py
import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any, TypeAlias

from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from opentelemetry import trace
from opentelemetry.trace import Span

from observability.agent_counters import InvocationCounters, invocation_counters
from observability.genai_attributes import (
    APP_AGENT_STEP_COUNT,
    APP_AGENT_TIME_TO_FIRST_CHUNK,
    GENAI_AGENT_NAME,
    GENAI_CONVERSATION_ID,
    GENAI_OPERATION_NAME,
    GENAI_REQUEST_STREAM,
)
from observability.metrics import record_agent_invocation
from observability.spans import error_type_of, mark_error, start_span

tracer = trace.get_tracer(__name__)

# The final graph state from ainvoke(), e.g. {"messages": [...]}.
AgentResult: TypeAlias = dict[str, Any]
# One "updates" StreamPart's data: {node_name: that node's state update}.
AgentUpdate: TypeAlias = dict[str, Any]


def record_agent_result(
    *, started_at: float, agent_name: str, error_type: str | None, counters: InvocationCounters
) -> None:
    """One duration and one pair of fan-out observations per invocation."""
    record_agent_invocation(
        duration_s=time.perf_counter() - started_at,
        agent_name=agent_name,
        error_type=error_type,
        inference_calls=counters.inference_calls,
        tool_calls=counters.tool_calls,
    )


async def invoke_agent(
    agent: CompiledStateGraph,
    messages: list[BaseMessage],
    *,
    agent_name: str,
    conversation_id: str | None = None,
) -> AgentResult:
    started_at = time.perf_counter()
    error_type: str | None = None

    # The callback and the tool middleware increment these; this wrapper is
    # the only thing that reads them. See ../../../metrics/genai.md.
    with start_span(
        f"invoke_agent {agent_name}",
        attributes={
            GENAI_OPERATION_NAME: "invoke_agent",
            GENAI_AGENT_NAME: agent_name,
        },
    ) as span, invocation_counters() as counters:
        if conversation_id:
            span.set_attribute(GENAI_CONVERSATION_ID, conversation_id)

        try:
            result = await agent.ainvoke({"messages": messages})
        except BaseException as exc:
            # start_span marks the span (cancellation is not ERROR); this
            # only labels the metric.
            error_type = error_type_of(exc)
            raise
        finally:
            record_agent_result(
                started_at=started_at,
                agent_name=agent_name,
                error_type=error_type,
                counters=counters,
            )

        # Bounded facts about how the agent behaved on this run.
        span.set_attribute("app.agent.message_count", len(result["messages"]))
        return result
```

Note what is **not** here: an `agent.duration` attribute. The span's own start and end times already carry that, and the metric carries the aggregate. A duplicate attribute is a second number to keep consistent with the first.

The `invocation_counters()` scope is what makes model-calls-per-invocation and tool-calls-per-invocation possible at all — nothing in LangChain counts them for you. The `ContextVar` it wraps, and the increments the callback and tool middleware make into it, are in `../../../metrics/genai.md`. `record_agent_result()` is shared by every wrapper so streaming cannot silently omit the required fan-out metrics.

---

## Streaming: this file owns the agent-level TTFC

`app.agent.time_to_first_chunk` — agent invocation to the first chunk the caller sees, including planning, retrieval, and tool calls. It is a different number from the model's `gen_ai.response.time_to_first_chunk` (`model_callback.md`) and from the API's first byte. The full taxonomy and why each needs its own attribute: `../attributes.md`.

## Stream modes

| `stream_mode` | Yields | Use for |
| --- | --- | --- |
| `"updates"` | state updates after each agent step | step-level progress; **not** token latency |
| `"messages"` | LLM tokens with metadata, as generated | token streaming and agent TTFC |
| `"values"` | the full state after each step | rarely useful for telemetry — large payloads |
| a list, e.g. `["updates", "messages"]` | both, interleaved and tagged | UIs that show progress and tokens |

**Do not compute TTFC from `"updates"`.** An update arrives when a graph node finishes, which is long after the first token left the model. It measures step completion and will be several times the real number.

Every template below passes `version="v2"` explicitly. LangGraph >=1.1 then
returns a `StreamPart` dictionary with `type`, `ns`, and `data` regardless of
whether one or several stream modes are selected. The v1 default yields tuples
for multiple modes; do not mix the two schemas. See `../../../compatibility.md`.

### The rule both streaming wrappers follow

The agent span is never current across a `yield`: `../provider_sdk.md`, "Why the
span is never current across a `yield`" (owner of the rule).

A streaming agent wrapper cannot simply stop making the span current, though:
the model callback and tool middleware create their spans *during* the agent's
work, and that work happens while the generator is **resumed**. So the span and
the invocation counters must be current for each resumption and not between
them. One helper says exactly that, and both wrappers use it:

```python
from collections.abc import Iterator
from contextlib import contextmanager

from observability.agent_counters import bind_counters


@contextmanager
def agent_step(span: Span, counters: InvocationCounters) -> Iterator[None]:
    """Make the agent span and its counters current for ONE resumption.

    Never put a `yield` of the streaming wrapper inside this. That is the
    entire point of it.
    """
    with trace.use_span(span, end_on_exit=False, record_exception=False):
        with bind_counters(counters):
            yield
```

Because each step must be bracketed, the wrappers iterate the stream
explicitly rather than with `async for`.

### Token streaming

```python
from observability.metrics import record_agent_time_to_first_chunk


def record_first_chunk(span: Span, *, started_at: float, agent_name: str) -> None:
    """Agent TTFC: the span attribute and the histogram, always together."""
    elapsed = time.perf_counter() - started_at
    # Organisation-owned: there is no standard agent-level TTFC attribute.
    # gen_ai.response.time_to_first_chunk belongs to a single model request,
    # not to an agent run.
    span.set_attribute(APP_AGENT_TIME_TO_FIRST_CHUNK, elapsed)
    record_agent_time_to_first_chunk(elapsed, agent_name=agent_name)


async def stream_agent_tokens(
    agent: CompiledStateGraph,
    messages: list[BaseMessage],
    *,
    agent_name: str,
    conversation_id: str | None = None,
) -> AsyncIterator[BaseMessage]:
    started_at = time.perf_counter()
    first_chunk_seen = False
    error_type: str | None = None
    counters = InvocationCounters()

    # The manual tracer.start_span(), not the start_span helper or
    # start_as_current_span: this function yields.
    span = tracer.start_span(
        f"invoke_agent {agent_name}",
        attributes={
            GENAI_OPERATION_NAME: "invoke_agent",
            GENAI_AGENT_NAME: agent_name,
            GENAI_REQUEST_STREAM: True,
        },
    )
    if conversation_id:
        span.set_attribute(GENAI_CONVERSATION_ID, conversation_id)

    try:
        with agent_step(span, counters):
            stream = agent.astream(
                {"messages": messages},
                stream_mode="messages",
                version="v2",
            ).__aiter__()

        while True:
            # The agent actually runs inside this block, so the span and the
            # counters are current exactly where the callback needs them.
            with agent_step(span, counters):
                try:
                    part = await stream.__anext__()
                except StopAsyncIteration:
                    break

            if part["type"] != "messages":
                continue
            token, metadata = part["data"]
            if not first_chunk_seen:
                record_first_chunk(span, started_at=started_at, agent_name=agent_name)
                first_chunk_seen = True

            # Outside agent_step: nothing of ours is current in the consumer.
            yield token
    except asyncio.CancelledError as exc:
        # A manual span (this function yields), so it applies start_span's
        # cancellation rule itself: outcome, not ERROR.
        error_type = error_type_of(exc)
        span.set_attribute("app.outcome", "cancelled")
        raise
    except BaseException as exc:
        error_type = error_type_of(exc)
        mark_error(span, exc)
        raise
    finally:
        record_agent_result(
            started_at=started_at,
            agent_name=agent_name,
            error_type=error_type,
            counters=counters,
        )
        # tracer.start_span() has no context manager, so the end is explicit.
        span.end()
```

### Step updates, or both at once

Same skeleton as `stream_agent_tokens`: the same signature (including
`conversation_id`), `GENAI_REQUEST_STREAM: True`, the `agent_step` bracketing,
the cancellation and error handling, and `record_agent_result` in `finally`.
Exactly these things differ:

| | Step updates (`stream_agent_updates`) | Both at once |
| --- | --- | --- |
| `stream_mode` | `"updates"` | `["updates", "messages"]` |
| Return type | `AsyncIterator[AgentUpdate]` | `AsyncIterator[dict[str, Any]]`, tagged `{"type": "update" \| "token", "data": ...}` |
| Extra local | `step_count = 0` | `step_count = 0` and `first_chunk_seen = False` |
| Agent TTFC | none — updates are step-granular, never token latency | on the first `"messages"` part, via `record_first_chunk` |
| `finally` | `span.set_attribute(APP_AGENT_STEP_COUNT, step_count)` before `record_agent_result` | the same |

The per-part branch replaces the token wrapper's lines from `if part["type"] != "messages":` through `yield token` (still outside `agent_step`):

```python
            # Step updates
            if part["type"] != "updates":
                continue
            step_count += 1
            yield part["data"]
```

```python
            # Both at once
            if part["type"] == "updates":
                step_count += 1
                yield {"type": "update", "data": part["data"]}
            elif part["type"] == "messages":
                token, metadata = part["data"]
                if not first_chunk_seen:
                    record_first_chunk(span, started_at=started_at, agent_name=agent_name)
                    first_chunk_seen = True
                yield {"type": "token", "data": token.content}
```

Because the call opts into v2, both single-mode and multi-mode streams use the
same dictionary shape. If the service deliberately stays on v1, put tuple
unpacking behind one adapter and pin that decision in its dependency lock.

---

## The generator must always finish

The rule, the FastAPI `StreamingResponse` guard, and the disconnect test are in
`../provider_sdk.md`, "The generator must always finish". For an agent the symptom
is an `invoke_agent` span missing from a trace whose model spans are present.

Also call the callback's `abandon_runs_older_than()` (see `model_callback.md`) here, so a cancelled stream does not leave model spans open too.

---

## Conversation correlation

The agent span is where `gen_ai.conversation.id` goes in a LangChain service — it is the root of each turn. Every wrapper above accepts and sets it.

The rule it implements (one trace per turn, never one trace per conversation, never a metric attribute) is in `../attributes.md`.

---

## Business attributes worth setting on the agent span

Read the agent's actual behaviour and record the bounded facts that would matter in a review:

| Attribute | Why |
| --- | --- |
| `app.agent.step_count` | Detects loops |
| `app.agent.stop_reason` | `completed` / `step_limit` / `guardrail` / `cancelled` — bounded |
| `app.agent.fallback.used` | Whether a model or workflow fallback fired |
| `app.outcome` | the closed service-wide set in [`../../../conventions/naming.md`](../../../conventions/naming.md#the-app-shape) |
| `app.workflow.version` | Which prompt/agent version produced this run |

Keep every value bounded — these are the ones you will want as metric dimensions too.

---

## Multi-agent workflows

When one user request coordinates several agents, add a workflow span above them:

```
invoke_workflow support_rag         gen_ai.operation.name=invoke_workflow
  invoke_agent triage_agent
  invoke_agent support_agent
    chat gpt-5
    execute_tool order_lookup
```

Use `invoke_workflow` for the coordinating process and `invoke_agent` for each agent execution. `gen_ai.workflow.name` on the workflow span; `gen_ai.agent.name` on each agent span.

---

## Verify before moving on

- Exactly one `invoke_agent <name>` span per invocation.
- Every model and tool span is a **child** of it, not a sibling. If they are siblings, context was lost — check that the agent runs in the same task/context where the span was made current, and that a streaming wrapper brackets each resumption with `agent_step`.
- **Streaming only, and easy to miss:** a span the *consumer* creates between two streamed chunks is a child of the request span, **not** of `invoke_agent`. If it nests under `invoke_agent`, the wrapper is holding the span current across a `yield`.
- Streaming runs have `app.agent.time_to_first_chunk`, and it is **larger** than the first model span's `gen_ai.response.time_to_first_chunk`. If they are equal, one of them is measuring the wrong thing.
- Both streaming wrappers record `gen_ai.invoke_agent.inference_calls` and `gen_ai.invoke_agent.tool_calls` once, with values matching child spans even on error or cancellation.
- Every stream call opts into v2 and consumes `StreamPart["type"]` / `["data"]`; no v1 tuple unpacking remains.
- Three turns of one conversation produce three traces sharing `gen_ai.conversation.id`.
- A cancelled stream still ends the agent span.
- `gen_ai.conversation.id` appears on no metric.

---

## Then

- metrics: `../../../metrics/genai.md`
- logging: the `python-logging` skill (`../../../../../python-logging/references/genai.md`)
- final checks: `../../../verification.md`
