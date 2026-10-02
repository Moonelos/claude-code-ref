# SDK Bootstrap

One module, one owner, one call at startup, one flush at shutdown.

## Contents

- [Provider ownership](#before-writing-anything-does-a-provider-already-exist)
- [Bootstrap module](#the-bootstrap-module)
- [Common startup and shutdown order](#startup-order)
- [Propagators and sampling](#propagators)
- [Verification and failures](#verifying-the-bootstrap)

---

## Before writing anything: does a provider already exist?

Two ways to configure the SDK, and they must not both be active in one process:

| Style | Who owns the provider |
| --- | --- |
| Code-based | Your startup module builds `TracerProvider`/`MeterProvider` |
| Zero-code (`opentelemetry-instrument ...`) | The launcher builds them from environment variables |

Mixing them yields duplicate spans, a no-op provider, or silently discarded telemetry. Check first:

```bash
grep -rn "set_tracer_provider\|TracerProvider(\|opentelemetry-instrument" \
  --include='*.py' --include='Dockerfile' --include='*.yaml' --include='*.sh' .
```

If the service already launches with `opentelemetry-instrument`, do **not** add `configure_observability()`. Add only what the launcher cannot produce: business spans, custom metrics, and — if you need a custom span processor — register it on the *existing* provider rather than building a second one:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

provider = trace.get_tracer_provider()
# A no-op or API-only provider means the launcher has not run yet. Fail here
# rather than silently attaching a processor to a provider that discards spans.
if not isinstance(provider, TracerProvider):
    raise RuntimeError("OpenTelemetry SDK must be configured before app startup")
provider.add_span_processor(MyCustomSpanProcessor())
```

Most services need no custom processor at all. The one case this skill covers is baggage enrichment, and only when the user asked for baggage — `../tracing/baggage.md` defines that processor.

The rest of this file assumes code-based setup, which is the default for a production service because it gives explicit control over processors, views, and shutdown.

Resolve the static resource values using `resource_identity.md` and the runtime
value using only the platform reference selected by `SKILL.md` before creating
any provider. The resource is immutable after provider construction;
discovering a Pod UID, container ID, ECS task ARN, or process UUID later is too
late.

---

## The bootstrap module

Configured once per process from explicit inputs; a second call raises, so a
reloader or fork mistake fails loudly instead of stamping the wrong identity.
Bootstrap builds `TelemetryConfig` from the service settings; nothing here
reads settings or the environment.

```python
# observability/tracing.py
from collections.abc import Sequence
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON


@dataclass(frozen=True)
class TelemetryConfig:
    resource_attributes: dict[str, str]  # service.namespace/name/version/instance.id, deployment.environment.name
    traces_endpoint: str
    metrics_endpoint: str
    bsp_max_queue_size: int
    bsp_max_export_batch_size: int
    bsp_schedule_delay_millis: int
    bsp_export_timeout_millis: int
    metric_export_interval_millis: int
    metric_export_timeout_millis: int


@dataclass(frozen=True)
class Providers:
    tracer_provider: TracerProvider
    meter_provider: MeterProvider


_providers: Providers | None = None


def configure_observability(
    config: TelemetryConfig, *, third_party_views: Sequence[View] = ()
) -> Providers:
    """Build and register the OTel providers. Raises on a second call."""
    global _providers
    if _providers is not None:
        raise RuntimeError("observability is already configured in this process")
    resource = Resource.create(config.resource_attributes)

    # Collector tail sampling assumed; see Sampling below for head sampling.
    tracer_provider = TracerProvider(resource=resource, sampler=ALWAYS_ON)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=config.traces_endpoint),
            max_queue_size=config.bsp_max_queue_size,
            max_export_batch_size=config.bsp_max_export_batch_size,
            schedule_delay_millis=config.bsp_schedule_delay_millis,
            export_timeout_millis=config.bsp_export_timeout_millis,
        )
    )
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=config.metrics_endpoint),
        export_interval_millis=config.metric_export_interval_millis,
        export_timeout_millis=config.metric_export_timeout_millis,
    )
    # Own instruments declare buckets at creation (../metrics/service.md);
    # views exist only for third-party instruments.
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[reader], views=list(third_party_views)
    )
    metrics.set_meter_provider(meter_provider)

    _providers = Providers(tracer_provider, meter_provider)
    return _providers


def shutdown_observability() -> None:
    """Flush and stop the providers. Safe to call more than once."""
    global _providers
    if _providers is None:
        return
    providers, _providers = _providers, None
    try:
        providers.tracer_provider.shutdown()
    finally:
        providers.meter_provider.shutdown()
```

Bootstrap resolves per-signal endpoints once (base plus `/v1/traces` unless a
per-signal override is set; see the OTLP/HTTP path trap in `package_layout.md`).

What each piece does:

| Piece | Role |
| --- | --- |
| `Resource` | Service identity stamped on every span and metric |
| `TracerProvider` | Creates tracers; owns sampling and span export |
| `BatchSpanProcessor` | Buffers and exports spans in batches — never use `SimpleSpanProcessor` in a request path |
| `MeterProvider` + `PeriodicExportingMetricReader` | Aggregates and exports metrics on an interval, independently of traces |
| `third_party_views` | Bucket boundaries for instruments this service does not create |
| `shutdown_observability()` | Clears its handles first, so a second call is a no-op |
| Second `configure_observability()` | Raises; one bootstrap call per process |

`service.instance.id` must be unique for the running service instance and
stable for its lifetime. `resource_identity.md` defines the common contract;
the selected runtime reference defines its source. Do not derive it from an
ambiguous gateway Collector or a shared replica name.

### About the batching settings

The `BatchSpanProcessor` values and the metric reader's `export_timeout_millis` use the SDK defaults in the variables table in `package_layout.md`. The metric export interval is the one deliberate deviation: **60 s is the SDK default, while the table uses 15 s.**

Keep these values in the service's settings object. Although the SDK can read the `OTEL_BSP_*` and `OTEL_METRIC_EXPORT_*` variables when an argument is omitted, passing an argument changes who owns configuration:

| Written as | Behaviour |
| --- | --- |
| argument omitted | env var wins, SDK default if unset |
| literal passed | the literal wins and the SDK ignores its environment variable |
| settings field passed, as above | the service config validates the environment value and supplies its documented default |

This keeps every deployment override in the same typed configuration path instead of splitting ownership between the application and the SDK. A 60-second metric interval means an alert cannot fire on data younger than a minute, which is usually too slow for a request-rate or error-rate alert. Shortening it costs more export requests and more series churn; leave the documented default at 15 s unless the metrics backend complains, and coordinate it with the Collector batch/export cadence.

Drops from an undersized queue are silent. If spans go missing only under load, this is the first thing to check — and the Collector's `otelcol_receiver_accepted_spans` next to the application's own export count is how you confirm it (`../collector/component.md`).

---

## Startup order

The failure this prevents: a client created before its instrumentation is installed may never produce spans, and never inject propagation headers, with no error anywhere.

```
process starts
  -> configure_observability()
  -> install process-wide client/library instrumentation
  -> create the application object
  -> instrument the application instance
  -> create long-lived clients and start background work
  -> serve traffic
```

Shutdown runs in reverse, and telemetry goes last:

```
stop background work
  -> close clients        (their close() may still finish spans)
  -> shutdown_observability()
```

Shutting the providers down before closing clients silently drops the final spans.

Load the runtime-specific startup file selected by `SKILL.md` after applying
this common order. Conditions compose: FastAPI under Gunicorn needs both the
FastAPI and pre-fork references.

---

## Propagators

Set the propagator explicitly in the deployment so services cannot drift apart
during a migration. Trace context is the default contract:

```bash
export OTEL_PROPAGATORS=tracecontext
```

If discovery approved an allowlisted cross-service baggage value and
`../tracing/baggage.md` was loaded, use `tracecontext,baggage` for the services
that participate. Do not enable baggage merely because the SDK supports it. If
services disagree about trace context propagation, the trace breaks at that
boundary with no error.

---

## Sampling

When discovery selects Collector tail sampling, use **100% head recording with an explicit `AlwaysOn` sampler** in the application, which means no head-side dropping. Head sampling cannot know that a request will fail or be slow, which is exactly the trace you want to keep. Do not omit the sampler from a code-owned `TracerProvider`: omission allows `OTEL_TRACES_SAMPLER` to change the policy implicitly.

The W3C sampled flag carries only this upstream decision, not the tail sampler's later keep/drop; why it never goes into logs as `trace_sampled` or counts as retention is in `../logging/correlation.md`.

If discovery instead selects head sampling, do **not** keep the hardcoded `ALWAYS_ON`. A code-owned provider receives the selected sampler explicitly, with the measured ratio coming from typed settings:

```python
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
tracer_provider = TracerProvider(resource=resource, sampler=ParentBased(root=TraceIdRatioBased(config.trace_sample_ratio)))
```

For zero-code provider ownership, the equivalent deployment configuration is:

```bash
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
```

The ratio above is illustrative, not a default; derive it from `../tracing/production_policy.md`. Keep one configuration owner: code plus typed settings for a code-owned provider, or environment variables for a zero-code provider.

Set sampling-relevant attributes at span *creation* time — a sampler cannot see attributes added later. Token counts are known only after the response, so keeping high-token traces needs tail sampling.

Sampling is never a privacy control. Content capture and redaction must be correct whether or not a trace is sampled.

---

## Verifying the bootstrap

Before writing any instrumentation, prove the pipeline works with the temporary
console exporter in `../verification.md` §1, and check exported histogram
boundaries per `../verification.md` §7.

---

## Common failures

| Symptom | Cause |
| --- | --- |
| No spans at all | Providers configured after the app served requests; wrong exporter package; unreachable Collector |
| Duplicate spans | Zero-code and code-based setup both active; instrumentor called twice; dev reloader re-imported the app |
| `404` from the Collector | Per-signal endpoint set to a bare `host:port` instead of the full `/v1/traces` path |
| Spans vanish in CLI jobs and serverless | No flush before exit |
| Spans missing in Gunicorn workers | SDK configured in the parent before fork |
| Traces break at one service | That service uses a different propagator set |
