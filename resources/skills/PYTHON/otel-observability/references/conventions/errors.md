# The Error Contract

Every code sample in this skill records failures the same way. This file owns
the span-error contract, `error.type`, and telemetry failure isolation; other
files link here instead of restating them.

General exception-handling shapes (broad `except`, translation, mislabelled
unknown failures) are owned by
`../../../python-service-architecture/references/errors.md` (Broad except
shapes; Never mislabel unknown failures). This file adds only the telemetry
parts.

## No span events

Do not call `span.record_exception()` or `span.add_event()`: not for
exceptions, not for checkpoints. The span carries status and bounded
attributes; exception detail travels as one correlated log record, which can be
retained, sampled, and redacted independently of the trace.

Some trace backends render an error's message and stack trace from the
`exception` span event. Before adopting this contract, confirm the backend can
pivot from a span to its logs by `trace_id`/`span_id`, and that the Collector
does not delete the log attribute the detail travels in
(`../collector/production.md`). If it cannot pivot, say so and let the user
choose.

## The contract

When an operation fails:

1. the span ends with `ERROR` status;
2. the span carries a bounded `error.type`;
3. the exception is logged once, by the owning boundary, while the span is
   still active (see [Exception detail](#exception-detail)).

Nothing else. No `str(exc)` in the span status message, no exception message
as an attribute, no log at every call depth.

## The span helper

Every sample calls one shared helper. It lives in the shared observability
library when one exists (`../setup/shared_library.md`), otherwise in the
service's `observability/` package. Before writing one, read the helper
signatures sibling services already use and reuse them verbatim.

```python
# observability/spans.py
import asyncio
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Link, Span, SpanKind, Status, StatusCode
from opentelemetry.util.types import Attributes

_tracer = trace.get_tracer(__name__)


def error_type_of(exc: BaseException) -> str:
    """The one place that turns an exception into a bounded error.type."""
    return type(exc).__name__


def mark_error(span: Span, exc: BaseException) -> None:
    span.set_status(Status(StatusCode.ERROR))
    span.set_attribute("error.type", error_type_of(exc))


@contextmanager
def start_span(
    name: str,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Attributes = None,
    links: Sequence[Link] = (),
    context: Context | None = None,  # Context() for a new root; None = current
) -> Iterator[Span]:
    with _tracer.start_as_current_span(
        name,
        context=context,
        kind=kind,
        attributes=attributes,
        links=links,
        record_exception=False,
        # This helper sets status itself, below, for every BaseException.
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except asyncio.CancelledError:
            span.set_attribute("app.outcome", "cancelled")
            raise
        except BaseException as exc:
            mark_error(span, exc)
            raise
```

Callers add attributes and outcome to the yielded span; they never catch just
to mark the span. A worked caller is the retrieval span in
`../tracing/genai/retrieval.md` ("One span per stage").

### `set_status_on_exception`

Ad-hoc spans pass only `record_exception=False` and leave
`set_status_on_exception` at its default. Only a generic helper that itself
catches `BaseException`, sets `ERROR` and `error.type`, and re-raises (the one
above) may disable it. A narrow `except SpecificError` does not make disabling
it safe: every other exception would leave the span `UNSET`, and error-biased
sampling then drops it.

### Cancellation

- Shutdown cancellation records `app.outcome=cancelled` without `ERROR`.
- A timeout is a failure: open the span outside `asyncio.timeout(...)` so it
  sees `TimeoutError` and records `ERROR` with `error.type=TimeoutError`. A
  span inside the timeout scope sees `CancelledError`; its enclosing span
  records the timeout.
- `except CancelledError: raise` next to `except Exception` is redundant;
  `CancelledError` is not an `Exception`. Cancellation-safe idioms are owned by
  `../../../python-service-architecture/references/async-and-lifecycle.md`
  (Cancellation-safe idioms).

## A failure handled inside the span

A context manager cannot infer failure from a caught exception. Mark the span
yourself, and only if the operation genuinely failed.

```python
def fetch_price(sku: str) -> Decimal | None:
    with start_span("fetch price") as span:
        try:
            return pricing_client.get(sku)
        except PricingTimeoutError as exc:
            mark_error(span, exc)
            log.error("price_fetch_failed", exc_info=exc, **{"error.type": error_type_of(exc)})
            return None
```

A successful fallback is a successful operation: record
`app.fallback.used=true` and leave status unset. Marking it failed breaks
error-rate alerts and error-biased tail sampling.

## A manually started span

Only inside framework callbacks where a context manager cannot be used
(callback pairs, middleware hooks) do you own status, attributes, and `end()`:

```python
span = tracer.start_span("chat gpt-5", attributes=request_attributes)
try:
    response = call_model()
except BaseException as exc:
    mark_error(span, exc)
    raise
else:
    span.set_attribute("gen_ai.response.model", response.model)
finally:
    span.end()
```

`tracer.start_span()` neither sets status on exception nor makes the span
current. Use `trace.use_span(span, end_on_exit=False, record_exception=False)`
if children must nest under it.

## `error.type` values

`error.type` is exactly one of:

- the exception class name, from the shared `error_type_of(exc)`;
- a provider status or error code the SDK exposes stably (`429`,
  `rate_limit_exceeded`); extract it once, in the shared library;
- a value of the service's documented closed error-code enum;
- a sentinel: `_OTHER` (a real failure that could not be classified) or
  `_ABANDONED` (the operation never reported an outcome: a dropped stream, a
  callback with no end event).

| Good | Bad |
| --- | --- |
| `TimeoutError` | `TimeoutError: pricing-api timed out after 3.0s` |
| `429` | `429 Too Many Requests for sku=ABC-123` |
| `_OTHER` | `type(exc)` repr, or the response body |

On success, omit `error.type`; `app.outcome` carries the split (closed value
set: `naming.md#the-app-shape`). Unwrap wrapper
exceptions (`RetryError` says nothing; its cause does). A business failure
taxonomy (declined, not fulfillable, policy violation) goes in
`app.failure.class`, not `error.type`. Cancellation is not a sentinel:
`CancelledError` and `GeneratorExit` are class names.

Add a custom exception only when its stable type or reason changes handling,
retry, alerting, or user-facing mapping; chain the cause with
`raise DomainError(...) from exc`. Classification bases and translation are
owned by `../../../python-service-architecture/references/errors.md`
(Classification bases; Translate once).

## Exception detail

The exception-detail rule (`exc_info=exc` only at call sites, the
`log_full_exception_trace` setting, safe vs full projection, record-size
limits) is owned by the `python-logging` skill
(`../../../python-logging/references/errors-and-security.md`, Exception detail).
The telemetry side is only this: spans never carry the exception message or
stack trace — the span gets `ERROR` status and bounded `error.type`, and the
owning log record carries the detail.

## Where the exception log goes

The boundary that decides the outcome logs it: the HTTP exception handler, the
worker's per-message handler, the job's top-level `try`. One record per failed
operation. Inner layers mark the span and re-raise. Handling boundaries are
owned by `../../../python-service-architecture/references/errors.md`
(Handling boundaries).

## Failures visible in both signals

Log severity and span status are independent. `log.error(...)` does not set the
span to `ERROR`, and tail sampling sees only span status: a failure logged with
its span `UNSET` is sampled away exactly when you need it. Set both at the
boundary that knows the operation failed.

An errored trace is any trace containing an `ERROR` span; filters and tail
sampling match any span, not only the root. Successful fallback, expected
business HITL, and safe deferral keep unset status plus their bounded outcome.
Terminal failure-driven HITL carries `ERROR`, `error.type`, and
`app.outcome=hitl`.

## Telemetry failure isolation

- Do not wrap OpenTelemetry API calls in `try/except`; the API is specified
  not to throw.
- Guard app-owned telemetry code (serializers, usage parsers) at most once, at
  the framework-callback or close boundary, with one `telemetry_failed`
  warning carrying `exc_info`. Never `except Exception: return`.
- Instrumentation wrappers record the failure and re-raise; business code
  decides whether to contain it.
- Telemetry observes an outcome; it never chooses or mutates it, and never
  enforces business behaviour such as cancellation.
- Replace `if telemetry is not None` branches with a no-op implementation.

## Checklist

- [ ] No `record_exception()` or `add_event()` in new code.
- [ ] Spans come from `start_span`; manual spans exist only in framework
      callbacks and pass `record_exception=False`.
- [ ] Only the generic helper disables `set_status_on_exception`.
- [ ] Every failure sets `error.type` from the allowed set; success omits it.
- [ ] Handled failures mark the span only when the operation actually failed.
- [ ] One owning log per failure, with `exc_info=exc`; exception-detail checks
      are in the `python-logging` skill.
- [ ] No exception message in a span attribute, status message, or metric.
- [ ] No `try/except` around OpenTelemetry API calls.
