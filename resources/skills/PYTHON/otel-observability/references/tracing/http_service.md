# Tracing an HTTP / API Service

The framework owns the request boundary. Your job is the layer underneath it: the business operations that explain why a request was slow or wrong.

The code here is **FastAPI**, which is what this skill supports. Everything
except the two framework hooks — the exception handler and the route-template
lookup — is framework-independent: span selection, route templates, outbound
calls, attributes, and streaming all apply unchanged to any ASGI or WSGI
framework whose instrumentation owns the `SERVER` span.

---

## The trace shape you are aiming for

One inbound request is one trace boundary. Continue valid incoming context when
present; otherwise the framework's `SERVER` span becomes the root. Add custom
child spans for meaningful business phases inside that trace — never start a
second application trace for a phase of the same request.

```
POST /orders                          SERVER   (auto-instrumentation)
  validate order                      INTERNAL (manual)
  SELECT customers                    CLIENT   (auto)
  price order                         INTERNAL (manual)
    POST pricing-service /quote       CLIENT   (auto)
  send order-events                   PRODUCER (manual)
```

Auto-instrumentation gives you the first, third, and fifth lines. You write the rest.

---

## Do not create a second server span

If FastAPI instrumentation is active, it already extracts inbound trace context and starts the `SERVER` span. Do not call `propagate.extract()` in a handler and do not open another root span — you would detach the trace from its caller.

A manual span inside the handler automatically becomes a child of the server span, because the server span is current. Open it with the shared `start_span` helper (`../conventions/errors.md`), which sets `ERROR` and `error.type` on failure:

```python
from observability.spans import start_span


@app.post("/orders")
async def create_order(body: OrderRequest) -> OrderResponse:
    with start_span("validate order") as span:
        span.set_attribute("app.order.line_count", len(body.lines))
        validate(body)
    ...
```

---

## Which operations deserve a span

Span an operation when its duration, failure, or decision would appear in an incident review. Concretely:

| Span it | Don't span it |
| --- | --- |
| A call to another service or provider | A getter, a mapper, a validator that never fails slowly |
| A database or vector-store query | A loop iteration |
| An expensive in-process computation (ranking, pricing, PDF render) | A logging call |
| A decision that changes the response (routing, guardrail, fallback) | A helper that only reshapes data |
| A queue publish | Reading a config value |

A useful heuristic: if the span's duration would always be under a millisecond and it cannot fail, it is an attribute on the parent, not a span.

Enrich the current span instead of creating one:

```python
def record_pricing_context(strategy: str, product_count: int) -> None:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("app.pricing.strategy", strategy)
        span.set_attribute("app.pricing.product_count", product_count)
```

---

## Route templates, not paths

`http.route` must be the template — `/orders/{order_id}`, not `/orders/12345`. Framework instrumentation does this correctly for registered routes. It cannot do it for a path parsed by hand inside a catch-all handler; if the service has one, set `http.route` yourself to a bounded value.

Raw paths in span names or metric labels create one time series per ID and will take down a metrics backend.

---

## Errors

Follow `../conventions/errors.md`. For an API specifically:

- a handled 4xx is usually **not** a span error — a validation rejection is the service working correctly;
- a 5xx is;
- decide once, in writing, whether client cancellations and timeouts count as failures, because the SLO and the alert both depend on it.

The exception handler is the owning logging boundary. Emit one structured record there with `exc_info=exc`, and let the inner spans carry only `error.type`. Public error mapping is owned by `../../../python-service-architecture/references/api-and-workers.md` (Public error mapping).

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from starlette.routing import Route

from observability.spans import error_type_of, mark_error


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # The server span is owned by FastAPI instrumentation, so mark it here.
    mark_error(trace.get_current_span(), exc)
    route = request.scope.get("route")
    log.error(
        "request_failed",
        exc_info=exc,
        **{
            "http.route": route.path if isinstance(route, Route) else "unmatched",
            "http.request.method": request.method,
            "error.type": error_type_of(exc),
        },
    )
    return JSONResponse(status_code=500, content={"detail": "internal error"})
```

---

## Outbound calls

Use the instrumented HTTP client and let it inject trace context. Do **not** call `propagate.inject()` for a request that HTTPX or `requests` instrumentation already handles — you would set the headers twice, and the second write may not be the one you expect.

Create the client after the instrumentor is installed. `../setup/sdk_bootstrap.md` covers the ordering and the lifespan pattern that guarantees it.

Manual injection is correct only for a transport no instrumentation owns — see `queue_messaging.md`.

---

## Attributes worth setting on the request

Set these at span creation where possible, so a sampler can use them:

| Attribute | Source |
| --- | --- |
| `http.route`, `http.request.method`, `http.response.status_code` | auto-instrumentation |
| `app.tenant.tier` — one key, everywhere (`../conventions/naming.md`) | authenticated identity |
| `app.workflow.name` | which product flow this endpoint serves |
| `user.id`, `session.id` | authenticated identity, if privacy policy allows — traces only, never metrics |
| `gen_ai.conversation.id` | GenAI services, see `genai/attributes.md` |

Derive them from the authenticated request, never from unvalidated request body fields. A caller-supplied "tenant tier" is a spoofable metric dimension.

### Attributes on custom business spans

Every custom span should explain its own operation without copying the whole
request. At creation, set its stable business operation/workflow and bounded
strategy, policy, or dependency identity. Before it ends, add the outcome and
the few result facts operators need — item/result counts, decision category,
fallback used, or retry attempt. On failure, add only bounded `error.type` and
status; the owning log carries the exception (python-logging skill).

Do not attach every available request field. IDs and user/session values belong
only where they materially help find one trace and privacy policy allows them;
they never become metric labels. Resource attributes are inherited and should
not be manually repeated on each span.

---

## Streaming responses

A streaming endpoint (SSE, chunked JSON) has two latencies that matter: time to first byte, and total duration. The server span's duration covers the whole stream. Record first-chunk latency explicitly:

```python
span.set_attribute("app.response.time_to_first_chunk", first_chunk_at - started)
```

`app.response.time_to_first_chunk` is the API's own first byte and belongs to the server span. It is **not** the model's first chunk, and on a GenAI endpoint it is not the agent's either — three different numbers, tabulated in `genai/attributes.md`. Confusing them hides where the latency actually is.

Make sure the span ends when the stream ends, including on client disconnect: a generator that is never fully consumed can leave a span open until the process exits. The rule and the guard are in `genai/provider_sdk.md`, "The generator must always finish"; never hold a span current across the generator's `yield` (same file, "Why the span is never current across a `yield`").

---

## Then

- metrics: `../metrics/service.md` — request duration, active requests, dependency latency, business counters;
- logs: the `python-logging` skill — `request_failed` from the owner; routine completion stays in
  access logs. Trace IDs: `../logging/correlation.md`;
- if the endpoint publishes to a queue: `async_handoffs.md` and
  `queue_messaging.md` for the producer side;
- if the endpoint calls a model: `genai/attributes.md` for the span vocabulary.
