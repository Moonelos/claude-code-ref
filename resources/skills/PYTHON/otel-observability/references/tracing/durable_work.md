# DB-Backed Work Queues and Durable State Machines

**Do not open this file unless the service coordinates work through a
database** — an outbox table, a claim/lease loop, `FOR UPDATE SKIP LOCKED`, or a
persisted state machine another process resumes. A broker-only service needs
`queue_messaging.md` instead, and loading both invites a hybrid that matches
neither transport.

Read `async_handoffs.md` with this file. A database row can be the
asynchronous carrier even when no broker exists. Examples include an outbox
table, a worker using `FOR UPDATE SKIP LOCKED`, a leased job row, and a
persisted state machine whose next transition is resumed by another process.

## Contents

- [Carrier shape](#carrier-shape)
- [Schedule atomically](#schedule-a-transition-atomically)
- [Resume with a link](#resume-a-transition-as-a-linked-trace)
- [Carrier lifecycle](#carrier-lifecycle-across-states-and-retries)
- [Attributes and next signals](#attributes-and-next-signals)

## Carrier shape

The row stores a **W3C trace carrier**, not an OpenTelemetry `Link`, a serialized
SDK `Context`, or a bare trace ID. A link needs the complete remote
`SpanContext`: trace ID, span ID, trace flags, and optional trace state. Use
either:

```text
otel_context JSON/JSONB = {"traceparent": "...", "tracestate": "..."}
```

or dedicated `otel_traceparent` and `otel_tracestate` string columns. Keep the
stored keys allowlisted and size-bounded. Do not persist baggage unless its
separate allowlist and privacy contract were explicitly requested.

## Schedule a transition atomically

Create one low-cardinality boundary span for the durable handoff. Inject while
that span is current, then write the carrier in the **same database
transaction** as the work item or state change that becomes runnable:

```python
from collections.abc import Mapping

from opentelemetry.propagate import inject

from observability.spans import start_span

TRACE_CONTEXT_LIMITS = {"traceparent": 256, "tracestate": 512}


def normalize_trace_carrier(carrier: object) -> dict[str, str]:
    if not isinstance(carrier, Mapping):
        return {}
    return {
        key: value
        for key, limit in TRACE_CONTEXT_LIMITS.items()
        if isinstance((value := carrier.get(key)), str)
        and 0 < len(value) <= limit
    }


def schedule_transition(repository: TransitionRepository, transition: Transition) -> None:
    with start_span(
        "schedule workflow transition",
        attributes={
            "app.workflow.name": transition.workflow_name,
            "app.workflow.state": transition.next_state,
            "app.workflow.run.id": str(transition.workflow_run_id),
        },
    ):
        carrier: dict[str, str] = {}
        inject(carrier)
        # This method owns one DB transaction: state/work visibility and its
        # trace carrier commit or roll back together.
        repository.make_runnable(transition, otel_context=normalize_trace_carrier(carrier))
```

The normal SQL client instrumentation may add a child span for the `INSERT` or
`UPDATE`. It does not replace the explicit durable-handoff span because a
database library cannot know that the row represents asynchronous work.

## Resume a transition as a linked trace

Durable state-machine transitions are normally delayed and independently
retried, so default to one new trace per transition attempt with a link to the
stored causal context:

```python
from opentelemetry import context as otel_context, trace
from opentelemetry.propagate import extract
from opentelemetry.trace import Link

from observability.spans import start_span


def run_transition(row: TransitionRow) -> None:
    carrier = normalize_trace_carrier(row.otel_context)
    # Empty base context prevents a poll-loop or DB-claim span from becoming
    # the accidental parent when the stored carrier is missing or invalid.
    incoming_ctx = extract(carrier, context=otel_context.Context())
    causal_ctx = trace.get_current_span(incoming_ctx).get_span_context()
    links = [Link(causal_ctx)] if causal_ctx.is_valid else []

    with start_span(
        "run workflow transition",
        context=otel_context.Context(),
        links=links,
        attributes={
            "app.workflow.name": row.workflow_name,
            "app.workflow.state": row.state,
            "app.workflow.attempt": row.attempt,
            "app.workflow.run.id": str(row.workflow_run_id),
        },
    ):
        state_machine.run(row)
```

The worker's `SELECT`, lease, or claim span is transport detail, not the causal
producer. Never keep a polling span current around `run_transition()`, and do
not make the transition a child of the database read. The stored carrier owns
the causal relationship.

## Carrier lifecycle across states and retries

- When a successful state schedules the next state, inject a fresh carrier
  from the span that makes that next state runnable. This produces a chain of
  linked traces across the state machine.
- Retrying the **same** work item keeps its original scheduling carrier, so
  every attempt links to the same causal producer. Record the attempt number;
  do not let a failed attempt silently rewrite its own causal origin.
- Fan-out writes the causal carrier with every created work item. Fan-in starts
  one root span with bounded links to the valid contexts of its inputs.
- Keep a stable `app.workflow.run.id` span attribute and `workflow_run_id` log
  field across the whole run. It is the cross-trace business correlation key;
  it is high-cardinality and must never become a metric attribute.
- Treat stored trace context as untrusted metadata, not authorization. Ignore
  invalid carriers and start an unlinked root rather than failing the work.

Verify the exported transition span, not merely the in-memory `links` list:

```text
run workflow transition
  trace_id       != stored producer/transition trace_id
  parent_span_id  empty
  links           one valid stored producer/transition SpanContext
  attributes      app.workflow.run.id and bounded workflow/state values
```

## Attributes and next signals

| Attribute | Why |
| --- | --- |
| `app.workflow.name`, `app.workflow.state`, `app.workflow.attempt` | Bounded state-machine dimensions that explain which transition ran |
| `app.workflow.run.id` | High-cardinality identifier for finding every linked trace in one durable workflow; spans and logs only |
| `app.outcome` | bounded, from the closed set in [`../conventions/naming.md`](../conventions/naming.md#the-app-shape) |

- metrics: `../metrics/service.md` — processing duration and retry counts;
  workflow names/states may be dimensions only when they come from a bounded
  registry, and run IDs never are;
- logs: the `python-logging` skill — `workflow_transition_started` and
  `workflow_transition_completed` with `workflow_run_id`; linked-trace
  correlation: `../logging/correlation.md`.
