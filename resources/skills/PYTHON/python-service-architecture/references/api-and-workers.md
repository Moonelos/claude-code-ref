# API, worker, and event-driven process templates

## FastAPI / HTTP API

```text
src/<package>/
├── main.py
├── bootstrap/
│   ├── app.py                      # create_app(), lifespan, ASGI app
│   └── runtime.py                  # Dependency graph and disposal
├── api/
│   ├── dependencies.py             # ApiRuntime Protocol, get_runtime, providers
│   ├── problems.py                 # Exception -> public error table and handlers
│   ├── middleware.py               # Cross-request transport mechanics, when used
│   ├── routes.py                   # Until a second router exists, then routers/
│   └── schemas.py                  # Only when the HTTP shape differs
├── application/
├── domain/
├── ports/
└── ...                             # adapters/, genai/, config/, db/, observability/
```

The tree lists roles, not required filenames. `bootstrap/app.py` owns the
FastAPI instance, lifespan, router registration, and framework instrumentation.

Routers validate and translate HTTP input, resolve request context, call one
public application action, and translate the result. They never execute SQL,
initialize clients, invoke LLM SDKs, or branch on business state.

**Typed dependencies.** Store the typed runtime on `app.state` once and expose
one accessor, `get_runtime(request) -> ApiRuntime`, where `ApiRuntime` is a
Protocol declared in `api/` and satisfied by bootstrap. Routes receive services
through `Annotated[X, Depends(provider)]` from `api/dependencies.py`; they never
touch `request.app.state`, `cast` it, look attributes up by string, or
re-validate what bootstrap validated. Group transport policy scalars into a typed
object (`SsePolicy`). Tests use `app.dependency_overrides`.

**Thin routes.**

- Every route declares a typed `response_model`; no `dict[str, Any]` and no
  `extra="allow"`.
- Status codes use `fastapi.status` names.
- Query and path parameters are constrained with `Annotated[int, Query(gt=0,
  le=...)]`, not `if` statements. Configured limits, cursor decoding, and
  continuation checks are application policy.
- Request bodies use `extra="forbid"`; response models keep the default.
- Per-route authorization uses route dependencies
  (`Security(require_scope(...))`), not method/path tables in middleware.
  Authorization that depends on domain state belongs to the application action.
- Reuse an application model as the response when it is deliberately the public
  contract (frozen, `extra="forbid"`); create `api/schemas.py` only when the HTTP
  shape differs. Never re-export domain types there.

**Errors.** One exhaustive exception-to-public-error table and envelope helper;
see [errors.md](errors.md#public-error-mapping).

**Streaming.** The application runs the whole execution and returns a typed
stream of business events, including the terminal outcome. `api/sse.py` only
encodes, sends heartbeats, and turns disconnects into cancellation.

Middleware handles cross-request transport mechanics only: authentication
extraction, correlation context, CORS, request logging, size limits.

## Long-running worker

```text
src/<package>/
├── main.py
├── bootstrap/
│   ├── runtime.py                  # Construct resources
│   └── supervisor.py               # Start/stop loops and task health
├── application/
│   ├── process_due_work.py         # Business action
│   └── submit_batch.py             # Independent business action
├── adapters/
├── ports/
├── config/
├── db/
└── observability/
```

The supervisor is the one owner that creates all loop tasks, holds the stop
event, and runs shutdown. Async mechanics are in
[async-and-lifecycle.md](async-and-lifecycle.md).

- Each loop is an object with `async def run(self, stop: asyncio.Event)` that
  calls a **public** single-iteration method (`tick()` or `poll_once()`). That
  method calls one application action and records the returned result.
- Every loop declares exactly one failure policy:
  - **contain:** catch around the iteration, log once with `exc_info`, back off
    (backoff from settings), continue; or
  - **fail fast:** log once and re-raise, letting liveness fail.

  A loop that must survive infrastructure failures catches the service's
  unavailable base ([errors.md](errors.md#classification-bases)) inside the loop.
- Use one shared stop-aware sleep:

  ```python
  async def wait_or_stop(stop: asyncio.Event, seconds: float) -> bool:
      """Return True when stop was requested before the timeout."""
      try:
          async with asyncio.timeout(seconds):
              await stop.wait()
      except TimeoutError:
          return False
      return True
  ```

- When more than two cycles share the same span, metric, log, and failure shape,
  route them through one `run_cycle(name, operation)` helper. Each cycle receives
  its one action, not the whole runtime.
- Shutdown: set the stop event, wait under `asyncio.timeout(grace)`, cancel what
  remains, then `gather(..., return_exceptions=True)`.
- Pause, admission, and batch-until-done decisions belong in domain or
  application objects, not in the loop body.

A scheduled batch or CLI that runs once has no supervisor: `main.py` enters the
runtime, invokes the action once, maps the outcome to an exit code, and exits
non-zero on failure.

## SQS, Kafka, or another broker

Broker code is a concrete adapter under root `adapters/`; there is no root
`messaging/`. Start with one flat module (`adapters/nats_publisher.py`) and
promote per [boundaries.md](boundaries.md#centralized-ports-and-adapters):

```text
src/<package>/
├── adapters/
│   └── aws/
│       ├── sqs_consumer.py          # Poll/receive/ack/nack boundary
│       ├── sqs_serialization.py     # AWS wire-envelope translation
│       └── sqs_publisher.py         # Only when publishing is used
├── application/
│   └── email_admission.py
└── ports/
    └── message_publisher.py         # Only if an application action publishes
```

The transport boundary owns polling and delivery batches, wire-envelope parsing
and validation, trace-context extraction and injection, visibility heartbeat,
offset commit, acknowledgement and redelivery, and transport-policy DLQ
decisions.

The application action owns business authentication or authorization,
idempotency and durable admission, classification and correlation, and state
transitions and handoff.

Broker adapters map outcomes; they do not own retry policy. The adapter maps a
typed application outcome to ack, nak (with a delay), or terminate, and the delay
policy is a domain function. Receipt handles and partition offsets never enter
application, domain, or ports.

## Hybrid API plus worker

A deployable may expose health/admin HTTP endpoints and run background
consumers from one composition root (`bootstrap/app.py`, `runtime.py`,
`supervisor.py`). FastAPI lifespan may enter `runtime()` and start the
supervisor. If API and worker become independently scaled or deployed, split
them into separate services and extract only stable shared contracts to a
library.

## Health and readiness

Health state shared by API routes and the supervisor has one explicit owner.
Liveness reports process life. Readiness reflects whether the process can accept
useful work: initialized dependencies, compatible schema, healthy progress, and
required external availability. Probe mechanics are in
[async-and-lifecycle.md](async-and-lifecycle.md#health-probes).
