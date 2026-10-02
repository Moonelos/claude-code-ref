# Testing Telemetry

Read this when the repository has a test suite and the work added logic that can
break silently: usage parsing, content serialization, redaction, streaming
bookkeeping, retry counting, or carrier propagation.

This is **not** a substitute for `verification.md`. Tests prove a helper is
correct; verification proves the deployed pipeline carries the result.

Test design in general (fixtures, doubles, async tests) is owned by the
`pytest` skill (`../../pytest/SKILL.md`); where tests and support code live is
owned by `../../python-service-architecture/references/testing.md`. This file
adds only the telemetry harness and what is worth asserting.

---

## The harness

Module-level tracers and instruments are the default: `trace.get_tracer()` and
`metrics.get_meter()` return proxies that bind to whatever provider is
registered later. So tests register **one** global SDK provider pair per
session and clear the span exporter per test. Never monkeypatch instruments or
`trace.get_tracer`.

```python
# service_tests/support/telemetry.py: the member's importable support package
from dataclasses import dataclass

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint, HistogramDataPoint
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@dataclass(frozen=True)
class TelemetryCapture:
    tracer_provider: TracerProvider
    span_exporter: InMemorySpanExporter
    meter_provider: MeterProvider
    metric_reader: InMemoryMetricReader

    def spans(self, name: str) -> list[ReadableSpan]:
        return [s for s in self.span_exporter.get_finished_spans() if s.name == name]

    def points(self, metric_name: str) -> list[NumberDataPoint | HistogramDataPoint]:
        data = self.metric_reader.get_metrics_data()
        if data is None:
            return []
        return [
            point
            for resource_metrics in data.resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
            if metric.name == metric_name
            for point in metric.data.data_points
            if isinstance(point, NumberDataPoint | HistogramDataPoint)
        ]


def install_capture() -> TelemetryCapture:
    """Register the global providers once per test session."""
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    # Simple, not Batch: the test sees each span the moment it ends.
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    # Pass the same third-party views production passes.
    meter_provider = MeterProvider(metric_readers=[metric_reader], views=[])
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)
    return TelemetryCapture(tracer_provider, span_exporter, meter_provider, metric_reader)
```

```python
# tests/conftest.py
from collections.abc import Iterator

import pytest

from service_tests.support.telemetry import TelemetryCapture, install_capture


@pytest.fixture(scope="session")
def _session_capture() -> TelemetryCapture:
    return install_capture()


@pytest.fixture
def telemetry(_session_capture: TelemetryCapture) -> Iterator[TelemetryCapture]:
    _session_capture.span_exporter.clear()
    yield _session_capture
```

- Metrics are cumulative across the session. Assert on points filtered by an
  attribute unique to the test, or compare a value before and after the action.
- Assert production names, units, and attribute keys, imported from the
  conventions module, not retyped.
- Code that owns global provider registration (`configure_observability`,
  `configure_logging`) is tested in a subprocess, because the global provider
  can be set only once per process.

---

## What is worth a test

Deterministic logic, not the SDK. Do not test that OpenTelemetry creates spans.

| Test | Catches |
| --- | --- |
| Usage adapter against a recorded provider response | A renamed SDK field, silently zeroing token counts |
| Same adapter with fields missing | Instrumentation raising inside a request |
| Content serializer with batched input, several generations, multimodal parts, tool calls | Merged conversations and dropped finish reasons |
| Capture off | Any payload attribute present at all |
| Capture on, oversized response | Truncation marked rather than unbounded growth |
| Empty stream, error after first chunk, cancelled stream, abandoned generator | Spans that never end, and chunk counts that disagree with capture |
| Carrier extraction from a valid, missing, malformed, and oversized carrier | A bad carrier failing the work, or silently authorizing it |
| Linked-consumer path | `context=None` where `Context()` was meant: assert `span.parent is None` plus one link |
| Retry of the same work item | A regenerated carrier breaking the causal link |
| Redaction canary (`api_key=`, Bearer token, AWS key) through each sink | A secret reaching a span attribute or log line |
| Span helper on success, failure, cancellation, and timeout | `UNSET` failures, or cancellation marked `ERROR` |
| Both success and failure paths of every recorder | An error rate whose denominator excludes errors |
| GenAI projection membership on a mixed business/GenAI/operational tree | An orphaned model leaf, a missing business ancestor, or DB/HTTP noise selected |
| No span events | `record_exception` or `add_event` sneaking back in |

For GenAI projection classification, build a realistic mixed tree (for example
`run ingestion -> index document -> invoke_workflow -> embeddings` plus an
unrelated DB or HTTP sibling) and assert, for spans carrying
`app.telemetry.category="genai"`: exactly one marked root; every marked span
with an in-trace parent has a marked parent; workflow, GenAI leaves, and real
business ancestors are marked; operational siblings are not; structural
ancestors gain no fabricated `gen_ai.operation.name`. That proves
classification only; Collector routing is proven by the exported-telemetry
invariants in `collector/genai_projection.md`, never
by re-implementing the filter in test code.

---

## Two examples

```python
def test_linked_consumer_starts_new_trace(telemetry: TelemetryCapture) -> None:
    producer_trace_id = publish_test_message()

    handle_message(received_test_message())

    (consumer,) = telemetry.spans(SPAN_PROCESS_PRICING_JOBS)
    assert consumer.parent is None
    assert [link.context.trace_id for link in consumer.links] == [producer_trace_id]


def test_duration_recorded_on_the_error_path(telemetry: TelemetryCapture) -> None:
    job_type = "test-error-path"  # unique attribute value isolates this test's points

    with pytest.raises(TimeoutError):
        run_failing_job(job_type=job_type)

    (point,) = [
        p for p in telemetry.points(METRIC_WORKER_JOB_DURATION)
        if p.attributes and p.attributes.get(ATTR_JOB_TYPE) == job_type
    ]
    assert point.attributes[ATTR_OUTCOME] == "error"
    assert point.attributes[ATTR_ERROR_TYPE] == "TimeoutError"
```

The second one is the test most worth having and least likely to be written: it
is the only thing that stops an error-rate metric from getting quieter as the
service gets worse.

---

## Then

- exported-telemetry acceptance: `verification.md`
- if a test cannot run in this environment, say so explicitly rather than
  claiming the path is covered (`verification.md`, "Report honestly")
