# Service and Business Metrics

Metrics detect fleet-level problems; traces explain individual requests. Neither substitutes for the other, and metrics must be emitted **independently of trace sampling** — a 5% trace sample cannot tell you the real error rate.

Metrics are not optional for a GenAI service either. GenAI metrics (`genai.md`) sit on top of these, not instead of them.

---

## Default suggested baseline by application shape

Adopt every row under the application's primary shape unless the named source
does not exist or an established equivalent already emits it. Compose shapes:
an HTTP service that also consumes a queue gets both baselines. Add the
dependency baseline whenever the app calls a database, provider, broker, or
downstream service. These are defaults to review, not a catalogue to copy into
an unrelated process.

For **every** app, the resulting set must answer: operation throughput, failure
rate, duration, current saturation/in-flight work where meaningful, and the one
or two domain outcomes the business actually monitors. Prefer a standard
instrument for the first four. During discovery, propose at least one bounded
`app.*` business counter or distribution when no standard metric expresses the
domain outcome; state its owner and operational question before adding it.

### HTTP / API service

| Metric | Instrument | Source |
| --- | --- | --- |
| `http.server.request.duration` | Histogram (`s`) | auto-instrumentation |
| `http.server.active_requests` | UpDownCounter | auto-instrumentation |
| `http.client.request.duration` | Histogram (`s`) | auto-instrumentation |
| `db.client.operation.duration` | Histogram (`s`) | auto-instrumentation |

Framework instrumentation emits these already. Check what you get before writing a custom counter that duplicates one — a duplicate with slightly different labels is worse than nothing, because two dashboards will disagree.

Traffic, error rate, and latency percentiles all come from the duration histogram's count, status labels, and buckets. You do not need a separate request counter unless you need a label the standard metric does not carry (an SLO good/bad marker, for instance).

That is also why the worker table below has **both** `app.worker.job.duration`
and `app.worker.jobs`, which looks like the duplication just warned against and
is not: the standard HTTP histogram already carries the outcome through
`http.response.status_code`, while a job has no such standard label. The counter
exists to carry `app.outcome`. If you drop it, you lose the outcome split; if
you add its HTTP equivalent, you gain nothing.

### Worker / queue consumer

| Metric | Instrument | Unit | Detects |
| --- | --- | --- | --- |
| `messaging.client.operation.duration` | Histogram | `s` | publish/consume latency |
| `app.worker.queue.depth` | ObservableGauge | `{message}` | backlog |
| `app.worker.oldest_message.age` | ObservableGauge | `s` | user-visible delay |
| `app.worker.job.duration` | Histogram | `s` | processing time |
| `app.worker.jobs` | Counter | `{job}` | throughput and failure rate, by `app.outcome` |
| `app.worker.jobs.in_flight` | UpDownCounter | `{job}` | concurrency and saturation |
| `app.worker.retries` | Counter | `{retry}` | retry storms |
| `app.worker.dead_letter` | Counter | `{message}` | messages given up on |

Queue depth alone is misleading — a depth of 1000 is fine if it drains in a second. Pair it with oldest-message age, which is the number that maps to user impact.

### Scheduled job

| Metric | Instrument | Detects |
| --- | --- | --- |
| `app.job.duration` | Histogram (`s`) | runs getting slower |
| `app.job.runs` | Counter, by `app.outcome` | failed runs |
| `app.job.last_success.timestamp` | ObservableGauge | a job that stopped running at all |

The third one matters most: a job that never starts emits no duration and no failure. Only an age-since-last-success can detect it.

### Any service with dependencies

Dependency latency and error rate per downstream, from the client instrumentation's duration histogram. If a dependency is called through a library with no instrumentation, add one histogram with a bounded `server.address` or a logical dependency name.

For outgoing HTTP calls, always cover this baseline, whether or not the service
has admission control or retries:

| Signal | Source / breakdown |
| --- | --- |
| Request attempts | Duration histogram count, by dependency and `http.response.status_code` when a response exists |
| 429 and 5xx rates | Matching status counts divided by all attempts for the same dependency and time window |
| Timeouts and connection failures | Failed attempts by bounded `error.type`; do not invent an HTTP status when no response exists |
| Request latency | Duration histogram (`s`), by dependency and bounded operation when useful |

Prefer the existing `http.client.request.duration` instrument. Verify that it
actually records these attributes and failure paths; supplement missing coverage
at the client boundary without duplicating an existing instrument or adding a
separate counter for each status code. Use bounded dependency names and operation
templates, never raw URLs or request/user IDs as metric labels.

Record every physical request attempt, including retries, exactly once. A 429
followed by a successful retry means two attempts: one 429 and one success.
Check SDK-internal retries too; a wrapper around the whole logical call can hide
them. Keep final job/call outcomes separate from attempt outcomes.

Apply the same status and latency breakdown to incoming HTTP requests through
`http.server.request.duration`, including 429 responses returned by the service.

### Baseline selection report

Before implementation, list the selected defaults and their source (`auto`,
`manual`, or existing library), plus any intentionally omitted row and why.
This makes “metrics enabled” a concrete contract rather than an exporter that
may emit nothing useful.

---

## Instruments and units

| Instrument | For | Not for |
| --- | --- | --- |
| Counter | monotonic totals | latency |
| UpDownCounter | in-flight work | totals |
| Histogram | distributions | a single current value |
| ObservableGauge | current state read at collection time | totals |

Units: `s` for duration (not `ms`), `By` for bytes, `{request}`/`{job}`/`{token}`/`{message}` for counts. Full naming rules in `../conventions/naming.md`.

Histogram buckets must match the domain. The default buckets are tuned for sub-second HTTP calls; every histogram that can exceed ~5 s, or counts tokens or rows, declares its boundaries at creation with `explicit_bucket_boundaries_advisory`, or every value lands in the overflow bucket and p95 becomes a lie. A central `View` is only for third-party instruments (`../setup/sdk_bootstrap.md`).

### One measurement, one instrument, one owner

- Before adding a counter, list the instruments that already count the event,
  including a histogram's `_count`. One measurement goes to one instrument.
- Each new instrument or attribute names the query, dashboard, or alert it serves.
- Each counter event has one owning call site. One metric name has exactly one
  producing service; grep the other services before adding it.
- Current state held in an object is an `ObservableGauge` whose callback reads
  it, registered once at the composition root. A sync `Gauge.set()` is only for
  a value computed at one well-defined point, with exactly one writer.
- Zero baselines only for instruments with a live writer in that process.
- New instruments use `app.<domain>.<noun>` with a UCUM unit and no `_total` or
  unit suffix. Renaming an existing name is an explicit migration: dual-emit,
  then remove.
- Instruments live in the service's existing metrics module; split by
  capability once it holds roughly fifteen.

---

## Defining instruments

Create them once at module load. Recording is cheap; creating is not.

```python
# observability/metrics.py
from collections.abc import Iterable

from opentelemetry import metrics

meter = metrics.get_meter(__name__)

LONG_JOB_DURATION_BUCKETS = [1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0, 7200.0]

job_duration = meter.create_histogram(
    "app.worker.job.duration",
    unit="s",
    description="Time to process one job, measured from dequeue to completion.",
    explicit_bucket_boundaries_advisory=LONG_JOB_DURATION_BUCKETS,
)

jobs = meter.create_counter(
    "app.worker.jobs",
    unit="{job}",
    description="Jobs processed, by outcome.",
)

jobs_in_flight = meter.create_up_down_counter(
    "app.worker.jobs.in_flight",
    unit="{job}",
    description="Jobs currently being processed.",
)


def register_queue_depth(backlog: BacklogTracker) -> None:
    """Called once from the composition root; the callback reads held state."""

    def observe(_: metrics.CallbackOptions) -> Iterable[metrics.Observation]:
        yield metrics.Observation(backlog.depth, {"messaging.destination.name": backlog.queue})

    meter.create_observable_gauge(
        "app.worker.queue.depth",
        callbacks=[observe],
        unit="{message}",
        description="Messages waiting in the queue.",
    )
```

Gauge callbacks run on the SDK's collection interval. They read state already
held in memory; a callback that calls a slow API blocks metric collection for
every metric in the process.

---

## Recording measurements

Use one helper so duration, count, and in-flight always move together and every path is covered.

```python
import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.util.types import AttributeValue

from observability.spans import error_type_of


@contextmanager
def measure_job(*, queue: str, job_type: str) -> Iterator[None]:
    attributes: dict[str, AttributeValue] = {
        "messaging.destination.name": queue,
        "app.job.type": job_type,
    }
    jobs_in_flight.add(1, attributes)
    started = time.perf_counter()
    final = {**attributes, "app.outcome": "success"}
    try:
        yield
    except asyncio.CancelledError:
        final["app.outcome"] = "cancelled"
        raise
    except BaseException as exc:
        final |= {"app.outcome": "error", "error.type": error_type_of(exc)}
        raise
    finally:
        jobs.add(1, final)
        job_duration.record(time.perf_counter() - started, final)
        jobs_in_flight.add(-1, attributes)
```

The `finally` is the point. Recording only on success produces an error rate whose denominator excludes errors — a metric that gets quieter exactly as the service gets worse.

Success omits `error.type`; `app.outcome` carries the split, with the same key
on spans and metrics (`../conventions/errors.md`). In a unit-of-work helper this
is one of the three signals closed on every exit path; combine it with the span
and failure log in one `work_boundary`-style helper rather than N manual close
calls.

---

## Cardinality is a hard limit

Every unique attribute combination is a time series. Backends fall over from this, and the failure is expensive and slow to undo. The allowed and forbidden attribute lists are in `../conventions/naming.md`; check them before adding any label.

Two attributes that pass that check by eye and are still wrong:

- **`error.type` from an unwrapped exception.** If the exception message ends up in the class name (some SDKs generate dynamic exception classes), normalize to a known set with an `_OTHER` fallback.
- **`app.tenant.tier` versus `app.tenant.id`.** The tier is a handful of values; the ID is unbounded. Use the tier.

---

## Business metrics

Read the service's business logic and add the small number of metrics that would actually be watched. Examples of the shape:

```
app.exception.reviews        Counter,   by app.outcome
app.exception.resolutions    Counter,   by resolution category
app.pricing.updates          Counter
app.pricing.product_count    Histogram, per run
app.worker.batch.items       Counter,   by app.outcome
```

Every name follows `app.<domain>.<noun>` (above). No `.count` on the counters,
and `.count`/`.result_count` only where the measured quantity really is "how
many", per `../conventions/naming.md`. Documents returned per retrieval query is
`app.retrieval.result_count`, owned by `genai.md`; do not add a second name for
it.

Each one needs a stated purpose before you add it:

- what question does it answer?
- who looks at it?
- what would a bad value mean?
- what is its cardinality budget?

If any of those has no answer, leave it out. Every metric has storage, query, alerting, and cognitive cost.

Business metrics are not a loophole for cardinality. `app.pricing.updates` labelled by `supplier_id` is still one time series per supplier.

---

## Verify

Export once and check the actual output:

Send one canary through the OTLP path and query the metrics backend for its
`service.name` and expected `app.*` instruments. Without a Collector, use an
in-process `ConsoleMetricExporter` with a short export interval; the checks
below apply to either output.

Confirm:

- the metric exists under its unsuffixed name with the expected UCUM unit
  (a Prometheus-compatible backend may append a unit or `_total` suffix on
  ingest; see the note below);
- label values are the bounded ones you intended — no IDs;
- the counter increments on **both** success and failure;
- histogram buckets actually contain your values, rather than everything in `+Inf`;
- long-job histograms expose the intended `1, 5, 10, 30, ... 7200` second boundaries;
- the series count is stable across a load test. Growing series count under steady traffic means a high-cardinality label slipped in.

Backends can rename metrics on ingest. Write alerts against the names the
selected backend actually exposes, not names inferred only from the code.
