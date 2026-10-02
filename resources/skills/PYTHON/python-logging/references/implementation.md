# Logging Implementation

Adapt these rules to the repository's language and logging library. In Python, prefer the existing `structlog` or stdlib `logging` setup; do not introduce `structlog` solely to rename a working structured logger.

## One central pipeline

The shared logging owner must apply, in a deterministic order:

1. level/severity normalization;
2. UTC timestamp;
3. static service identity;
4. request/job/workflow context;
5. active trace correlation when available;
6. exception normalization and detail policy;
7. recursive secret and policy redaction;
8. JSON serialization and delivery.

Enrichment and redaction must run before rendering. Configure the pipeline once at process startup, before application modules emit records. Do not let a library call `basicConfig`, replace root handlers, or own shutdown behind the application's back.

Use one-line JSON in deployed environments. Keep keys and value types stable. Timestamp values use ISO 8601 UTC or the platform's documented canonical format. Configure log level through the existing typed settings object rather than scattered environment reads.

## Canonical envelope

A normal record should resemble:

```json
{
  "timestamp": "2026-08-10T09:12:44.113Z",
  "level": "info",
  "event": "workflow_transition_completed",
  "service.name": "order-worker",
  "workflow_run_id": "wf-123",
  "workflow_state": "capture_payment",
  "attempt": 2,
  "duration_s": 0.482,
  "outcome": "success"
}
```

Use native JSON numbers and booleans, not strings. Avoid null-filled universal schemas; omit fields that do not apply unless downstream schema requirements say otherwise.

## Call sites

- Declare `logger = logging.getLogger(__name__)` (or the structlog equivalent) once, below the imports; never call `getLogger` inline per call.
- The first positional argument is the snake_case past-tense event name, never a sentence or interpolated values.
- One call-site API per repo: stdlib `extra=` or structlog keyword arguments, not both. Record the choice in the shared logging library's module docstring.

Example: `logger.info("payment_declined", extra={"order_id": order_id, "reason": reason_code})`.

## Field allowlists

If the formatter applies a field allowlist, reconcile every new event against it: register each authored field with an agreed name and type, or omit it at the call site, and verify the serialized record still answers the event's question. The allowlist never silently discards an authored field: it fails in tests on unknown keys, or emits a dropped-fields marker in production. The same formatter may validate the event-name pattern. Allowlisting runs before redaction and serialization, never instead of redaction.

## Context lifecycle

Bind execution context at the real boundary and clear it in `finally`: HTTP middleware (request ID, route, permitted tenant), queue consumer (message/job ID, queue, attempt, workflow ID), scheduled job (job type, run ID), workflow transition (run ID, state, attempt).

Context-local storage must be safe for the runtime's concurrency model. Test concurrent requests or jobs to prove fields do not leak. A long-running worker must clear context between units of work.

Accept incoming correlation IDs only after validating length and character set. Generate one at the boundary when absent if the application needs request correlation. Do not reuse a producer's request ID as the current job ID; carry both under distinct names when both matter.

## Optional trace correlation

If the application already has OpenTelemetry or another tracing system, add its valid active `trace_id` and `span_id` in the central enricher, and omit them when no valid context exists. The tracing owner supplies that enricher and owns the ID format, linked traces, and sampling interactions; for OpenTelemetry it is `$otel-observability` (fallback `../../otel-observability/references/logging/correlation.md`, which covers the 32/16-hex format, `causal_trace_id`, and orphan logs from trace sampling).

Do not add OpenTelemetry packages, exporters, OTLP configuration, or a Collector merely to satisfy logging. Whatever the tracing system, never emit an upstream or linked trace ID as the current `trace_id`. Trace sampling does not sample logs: design log volume independently ([Volume controls](structlog-pipeline.md#volume-controls)).

## Libraries and third-party logs

Route application and library records through one final schema when practical. Preserve the original logger name under `logger` or `logger.name`. Apply explicit level overrides only to known noisy namespaces. Do not discard warnings/errors from an entire dependency namespace to silence one noisy event.

Access logs may remain under the framework's owner. Ensure they are structured and correlated when operators depend on them, but do not create a second routine request-completion event with the same purpose.

## Startup and shutdown

Configuration-validation failures that occur before logging initializes go to stderr without secrets. Buffering or asynchronous handlers must flush within the runtime's shutdown budget. CLIs, batch jobs, workers, pre-fork servers, and serverless runtimes require explicit lifecycle verification; a successful function return does not prove the final record was delivered.
