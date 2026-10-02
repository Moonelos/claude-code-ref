# Log–Trace Correlation

Application logging — event catalogue, schema, pipeline, redaction, exception
detail, GenAI log rules, testing — is owned by the `python-logging` skill
(`../../../python-logging/SKILL.md`). Load it for any logging work. This file
covers only what tracing adds: getting from a log line to its span and back.

Logs leave through python-logging's sink (stdout, file, or platform agent).
This skill does not configure OTLP log export or an OTel `LoggerProvider`. The
Collector configs keep a `logs` pipeline, which stays idle until OTLP log export
is added deliberately — with one delivery path per record.

## Trace-context processor

One enricher, passed to python-logging's central pipeline (its
`../../../python-logging/references/structlog-pipeline.md` shows the
`correlation` slot). It does not configure
logging itself.

```python
# observability/logging.py
from opentelemetry import trace
from opentelemetry.trace import format_span_id, format_trace_id
from structlog.typing import EventDict, WrappedLogger


def add_otel_trace_context(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = format_trace_id(context.trace_id)
        event_dict["span_id"] = format_span_id(context.span_id)
    return event_dict
```

Bootstrap order: `configure_observability(...)`, then
`configure_logging(logging_config(settings), correlation=[add_otel_trace_context])`.
The processor must run before the renderer.

`trace_id` is 32 lowercase hex characters, `span_id` is 16. The enricher writes
them only for a valid span context, so they never appear as zeros: they are
either correct or absent. Absent means the call happened outside an active
span — or, when only logs from a background task, thread, or executor lack them
while the request's own logs have them, that task lost context when it was
scheduled (`../tracing/worker_runtime.md`).

Do **not** add `trace_sampled` to logs when the Collector owns tail sampling.
The W3C sampled bit records the SDK's head decision; with the `AlwaysOn`
sampler required by `../setup/sdk_bootstrap.md` it is always true, even for a
trace the Collector later drops, so never read it as effective retention.
Measure retention with Collector/backend counts (`../tracing/production_policy.md`).

### `LoggingInstrumentor`

Do not also use `LoggingInstrumentor` when the root logger routes through the
pipeline above. If a service keeps a separate stdlib formatter,
`LoggingInstrumentor().instrument(inject_trace_context=True)` injects
`otelTraceID`, `otelSpanID`, `otelTraceSampled`, and `otelServiceName`; map them
to `trace_id`, `span_id`, and `service.name` in that formatter and omit
`otelTraceSampled` for the reason above. `set_logging_format=True` calls
`logging.basicConfig()` and is the wrong owner when formatting already exists.
On `0.65b0` the instrumentor also installs an OTel export handler by default;
set `OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION=false` so records do not leave by two
paths.

## Linked traces and durable workflows

A log record has one current `trace_id`/`span_id` pair. Parent relationships
and `SpanLink`s belong on spans and are not copied into logs.

```text
producer trace A
  -> persisted carrier in work row

worker trace B, SpanLink -> A
  -> worker logs use trace_id B and the current worker span_id
```

Never put trace A's ID into the worker log's `trace_id`; it breaks
log-to-span navigation. For a workflow that crosses several linked traces, the
cross-trace search key is a business ID with one documented mapping:

```text
span attribute  app.workflow.run.id
log field       workflow_run_id
metric label    never — high-cardinality
```

If the trace backend cannot navigate links, a boundary log such as
`workflow_transition_started` may carry `causal_trace_id`, only for a
demonstrated query need.

## Don't mirror the trace into the logs

| Fact | Belongs in |
| --- | --- |
| Describes the whole operation (model, duration, token counts, outcome) | span attribute |
| A point-in-time occurrence needing its own timestamp and severity | log record |
| Needs to be queryable without opening a trace | log record |
| Detail of a failure — message, stack trace | log record, once, at the owning boundary |

Exception detail never goes on span events (`../conventions/errors.md`).

## Trace sampling does not sample logs

Tail sampling operates on traces. When a trace is dropped, its logs still flow:

```
log backend    records with trace_id=abc123
trace backend  no trace abc123
```

These orphan logs are normal. Aligning the two needs a stateful component
buffering logs by trace ID — build it only against a strict retention
requirement. The default is independent retention: traces keep failed and slow
traces and sample the rest; logs are retained by severity through the log
pipeline or backend (python-logging's volume controls), never through the trace
sampler.

`log.error(...)` does not set span status. A failure logged while its span
stays `UNSET` is sampled away exactly when you need it — set both at the owning
boundary (`../conventions/errors.md#failures-visible-in-both-signals`).

## GenAI backends

`CAPTURE_AI_CONTENT` governs span attributes only; it never authorizes content
in logs (`../../../python-logging/references/genai.md`). Langfuse's OTLP endpoint ingests traces
only: prompts and outputs reach it as span attributes, never as log records.
`gen_ai.conversation.id` may appear on spans and logs, never on metrics.

## Verify

- A log emitted inside a span has a 32-hex `trace_id` and a 16-hex `span_id`,
  and that trace ID finds the trace in the trace backend.
- A log emitted outside any span has no `trace_id` field (not zeros).
- For a new trace with a link, worker logs carry the worker trace ID, never the
  linked producer trace ID; `workflow_run_id` finds the complete durable run.
- Durable workflow boundary logs and transition spans share the documented
  `workflow_run_id` / `app.workflow.run.id` value; the ID appears on no metric.
- With a GenAI projection, a log's trace ID finds the operation in both trace
  backends; a log from a span the projection omitted is expected to have no
  observation-level `span_id` match there.
- A stdlib library record carries the same correlation fields as an
  application record.
- Each record reaches the log backend exactly once.
