# Event Design

Read the application's real boundaries and business logic before choosing events. Framework access logs and generic messages such as "processing" do not form an event catalogue.

## What earns a record

Log an occurrence when at least one is true:

- a domain state changed or an irreversible/external side effect occurred;
- a bounded decision changed the path: approved, rejected, routed, blocked, deferred, or fallback selected;
- work was retried, abandoned, dead-lettered, partially completed, or recovered;
- an operator will search for it by a business identifier;
- it needs its own timestamp or severity;
- it is the terminal outcome of an execution boundary.

Do not log getters, loop iterations, successful helpers, health-check success, or every step in a pipeline. For every proposed event, write the question it answers. If no concrete operational, support, audit, or business question exists, omit it.

## Baseline catalogue

Choose only rows matching real boundaries:

| Shape | Candidate events |
| --- | --- |
| Process | `application_started`, `application_stopping` |
| HTTP/API | `request_failed`; routine success belongs in access logs unless a business outcome must be independently searchable |
| Worker/consumer, scheduled job, CLI | `job_failed` from the owner plus one terminal business event (for example `invoice_issued`, `queue_message_dead_lettered`); no default `job_started`/`job_completed` pair |
| Durable workflow | `workflow_transition_started`, `workflow_transition_completed`, `workflow_transition_failed` |
| Retry/fallback | see "Loops and pollers" |
| Domain change | a past-tense event such as `order_approved`, `payment_declined`, `document_published` |

On very hot boundaries, omit or sample routine start/completion records. Keep failure events, audit-relevant changes, and consequential external side effects.

## Loops and pollers

In a long-running loop or retry policy, count every failure but log only on state transitions: healthy→failing once with `exc_info`, failing→recovered once with the failure count and duration. A recovered attempt, inner or retried, is counted, not logged, and produces no terminal error; an activated fallback emits one warning. A condition already exported as a gauge is alerted from the metric, not from repeated log lines.

## Naming

The `event` value is stable, lowercase `snake_case`, and describes what happened. Variable information is a field.

Good: `queue_message_received`, `payment_declined`. Bad: `processing`, `done`, `error`, `payment declined for order 8412`.

Do not encode severity, environment, IDs, counts, exception messages, or timestamps in event names.

## Event schema

Use a common envelope and add only fields that explain or locate the event:

```text
identity       timestamp, level (or established severity field), event, service.name
execution      request_id/job_id, trace_id/span_id when available, attempt
business       operation, workflow_state, decision/reason, outcome, counts
search         order_id, workflow_run_id, tenant_id when policy permits
failure        error.type, stable error/code, exception.stacktrace on the owner
```

Field names are lowercase and stable. Prefer dot-separated semantic namespaces already established by the project; preserve conventional flat identifiers such as `request_id` when changing them would split existing queries. One field must not change type between events.

High-cardinality identifiers are often appropriate in logs because they locate one occurrence. Their usefulness does not override privacy, retention, or access-control policy.

## Event ownership

Choose one owner for boundary outcomes. A framework access record and an application business record may both exist only when they answer different questions. Do not emit a new success record merely for symmetry with a failure record.

For an exception that crosses layers, the outer boundary deciding the HTTP response, message disposition, or job result owns the single terminal error record; a recovered inner attempt follows "Loops and pollers".
