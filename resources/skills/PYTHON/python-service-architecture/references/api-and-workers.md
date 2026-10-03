# API, worker, and event-driven process templates

## FastAPI / HTTP API

```text
src/<package>/                      # no main.py: `uvicorn --factory <package>.bootstrap.app:create_app`
├── bootstrap/
│   ├── app.py                      # create_app(), lifespan, ASGI app: the process owner
│   └── runtime.py                  # Dependency graph and disposal
├── api/
│   ├── dependencies.py             # ApiRuntime Protocol, get_runtime, RuntimeDep
│   ├── exception_handlers.py       # Exception -> public error table and handlers
│   ├── middleware.py               # Cross-request transport mechanics, when used
│   ├── schemas.py                  # Only when the HTTP shape differs
│   ├── sse.py                      # Event-stream encoder, when a route streams
│   └── routers/                    # One module per resource, each exposing `router`
│       ├── health.py               # Technical probes
│       └── <resource>.py           # Business routes
├── application/
├── domain/
├── ports/
└── ...                             # adapters/, genai/, config/, db/, observability/
```

The tree lists roles, not required filenames, but the shape is fixed: routes
live in `api/routers/`, one module per resource, from the first route. A flat
`api/` of `conversations.py`, `health.py`, `streaming.py` beside the plumbing is
wrong; so is a single `routes.py` that later has to be split. Plumbing
(`dependencies.py`, `exception_handlers.py`, `middleware.py`, `schemas.py`,
`sse.py`) stays
at the `api/` root; ASGI middleware never goes in `routers/`. Group routes by
resource, not by transport: streaming endpoints belong to their resource's router
(`turns.py`), while `api/sse.py` holds only the event encoder. `bootstrap/app.py`
owns the FastAPI instance, lifespan, router registration, and framework
instrumentation.

Business routers validate and translate HTTP input, resolve request context,
call one public application action, and translate the result. Technical routes
(liveness, readiness, metrics, version) call no action; see
[Health and readiness](#health-and-readiness). They never execute SQL,
initialize clients, invoke LLM SDKs, or branch on business state to decide
what happens. Matching on a returned state union to build the response shape is
translation, not a business branch.

**Typed dependencies.** Store the typed runtime on `app.state` once and expose
one dependency for it in `api/dependencies.py`: an `ApiRuntime` Protocol whose
read-only properties are what routes read (bootstrap's `Runtime` satisfies it),
`get_runtime(request)`, and `RuntimeDep = Annotated[ApiRuntime,
Depends(get_runtime)]`. The executable version is
[`api/dependencies.py`](../assets/canonical_service/src/my_service/api/dependencies.py)
in the canonical service, beside the identity dependency a write route takes
(`WriteIdentity`: the verified client, never a body field).

Routes take `runtime: RuntimeDep` and pass its fields to the action. There is no
provider per service: a `get_submission_store` that returns
`runtime.submission_store` only forwards. Routes never touch
`request.app.state`, `cast` it, look attributes up by string, or re-validate
what bootstrap validated. Group transport policy scalars into a typed object
(`SsePolicy`). Tests override `get_runtime` through `app.dependency_overrides`
with a runtime built from fakes.

**Thin routes.**

- Every route declares a typed `response_model`; no `dict[str, Any]` and no
  `extra="allow"`.
- Status codes use `fastapi.status` names.
- Query and path parameters are constrained with `Annotated[int, Query(gt=0,
  le=...)]`, not `if` statements. Configured limits, cursor decoding,
  selection building, and continuation checks are application policy: they live
  in the action or `domain/`, never inline in the route.
- Request bodies use `extra="forbid"`; response models keep the default.
- A required role or scope is checked twice: by a route dependency
  (`Security(require_scope(...))`) for a fast 403 before any I/O, and by the
  action or domain decision that relies on it, so another entry point cannot
  skip it. Never method/path tables in middleware. Authorization that depends
  on domain state belongs only to the action.
- Reuse an application model as the response when it is deliberately the public
  contract (frozen, `extra="forbid"`); create `api/schemas.py` only when the HTTP
  shape differs. Never re-export domain types there.

**Errors.** One exhaustive exception-to-public-error table and envelope helper;
see [Public error mapping](#public-error-mapping).

**Streaming.** The application runs the whole execution and returns a typed
stream of business events, including the terminal outcome. `api/sse.py` only
encodes, sends heartbeats, and turns disconnects into cancellation. The route
returns before execution ends, so the streaming action may record its own
execution through one observation object from `observability/`: it activates
the span around each execution step, records first output at most once and
exactly one terminal outcome per execution where the relevant facts are
available, passes the exception when recording failure, and closes the
observation in `finally`. The route and middleware record transport telemetry
only, never the application outcome or its failure record again.

Middleware handles cross-request transport mechanics only: authentication
extraction, correlation context, CORS, request logging, size limits.

## Public error mapping

Map exceptions to public errors in one exhaustive table in `api/`, keyed by
exception type (resolved along the MRO) or by a closed `StrEnum`. A test asserts
every exception a request can raise is mapped; errors raised only at startup
(policy validation) never reach HTTP and stay out of the table.

- Business exceptions state what happened. They do not carry `public_message`,
  `status_code`, or `retryable`.
- No `getattr(exc, "code")` resolution, no synthetic exceptions raised only to
  reach the mapper, no path branching in global handlers; one helper builds the
  response envelope.
- Routers do not `try`/`except` merely to re-raise.
- Route dependencies (authentication, scope checks) raise API-owned exception
  types registered in the same table, never `HTTPException(detail=<code>)`,
  which would need a second, string-keyed table the exhaustiveness test cannot
  see. Framework-raised 404 and 405 still get one handler.
- A code persisted in durable state is a `StrEnum` in `domain/`.
- Use a closed allowlist and `application/problem+json`; never copy exception
  text into the response; log only status >= 500 at the handler; send
  `Cache-Control: no-store` and `Retry-After` when retry metadata exists.

The canonical service's
[`api/exception_handlers.py`](../assets/canonical_service/src/my_service/api/exception_handlers.py)
is a complete table, and its `tests/unit/test_api.py` is the exhaustiveness
test.

## Long-running worker

Loops and queue consumers are business entry points, like routes. They live in
root `workers/`, the non-HTTP counterpart of `api/`: each worker parses its
input, calls one application action, records the result, and settles the
delivery. `bootstrap/supervisor.py` runs them and knows nothing about what they
do.

```text
src/<package>/
├── main.py
├── bootstrap/
│   ├── runtime.py                  # Builds every implementation, once
│   └── supervisor.py               # Tasks, cadence, stop event, failure policy, shutdown
├── workers/
│   ├── runtime.py                  # WorkerRuntime Protocol: what workers read
│   ├── inbox.py                    # Inbound delivery contract, when a consumer exists
│   ├── paid_orders.py              # Consumer: receive → action → settle
│   └── stuck_orders.py             # Periodic: one action per iteration → log summary
├── application/
│   ├── process_paid_order.py
│   └── reattempt_stuck_orders.py
├── adapters/sqs_inbox.py           # Implements the inbox over SQS
├── ports/
├── db/
└── observability/
```

**Why a separate package.** A worker is where delivery meets the use case: it
holds receipt handles, maps outcomes to acknowledgements, and logs results.
None of that is wiring, so it does not belong in `bootstrap/`; none of it is
business, so it does not belong in `application/`; and the SQS client should not
know which action handles its messages, so it does not belong in `adapters/`.

**Execution ownership.** `workers/` owns receiving or claiming work, delivery
leases and heartbeats, capacity/backpressure, per-item execution and settlement.
`application/` owns the business operation, including business retry and
admission decisions. `bootstrap/` constructs dependencies and owns process
startup, supervision, and shutdown. It starts and stops workers through their
execution and drain functions; the worker owns its in-flight delivery tasks.
A worker need not be as thin as an HTTP route: heartbeat, cancellation, and
backpressure are substantive entry-point behavior, not reasons to move business
logic out of an action or delivery mechanics into bootstrap.

Its imports follow the `api/`, `workers/` row of
[The core rule](boundaries.md#the-core-rule): like `api/`, it reads
implementations through a typed runtime view.

```python
# workers/runtime.py
class WorkerRuntime(Protocol):
    """What workers read from the runtime; bootstrap's `Runtime` satisfies it."""

    @property
    def paid_orders(self) -> Inbox[PaidOrder]: ...
    @property
    def shipment_store(self) -> ShipmentStore: ...
    @property
    def carrier(self) -> Carrier: ...
    @property
    def retry_policy(self) -> RetryPolicy: ...
```

### One iteration is a worker function

A worker is a plain `async def` taking the runtime view and returning whether
more work is due now. The supervisor calls it in a loop.

```python
# workers/stuck_orders.py
async def reattempt_stuck(runtime: WorkerRuntime) -> Iteration:
    summary = await reattempt_stuck_orders(
        store=runtime.shipment_store, carrier=runtime.carrier, policy=runtime.reattempt_policy
    )
    log.info("stuck_orders_reattempted", shipped=summary.shipped, failed=summary.failed)
    return Iteration.MORE_DUE if summary.more_due else Iteration.IDLE
```

- The action decides whether a full batch means more work (`summary.more_due`);
  the worker only translates that into `Iteration`. Batch-until-done, pause,
  and admission decisions never live in the worker or the supervisor.
- The worker is the *caller* that records telemetry from the returned summary
  ([boundaries.md](boundaries.md#observability)).
- `Iteration` (`IDLE`, `MORE_DUE`) is the one type the supervisor and workers
  share; define it in `workers/runtime.py`.

### The supervisor runs workers

The supervisor is the one owner that creates the process-level loop tasks, holds the stop
event, applies each loop's cadence and failure policy, and runs shutdown. It is
generic: one `run_loop` for every worker.

```python
# bootstrap/supervisor.py
async def run_loop(
    *, name: str, iteration: Callable[[], Awaitable[Iteration]], cadence: LoopCadence,
    stop: asyncio.Event, health: ProcessHealth,
) -> None:
    while not stop.is_set():
        try:
            outcome = await iteration()
        except DependencyUnavailableError:
            log.warning("loop_degraded", loop=name, exc_info=True)
            if await wait_or_stop(stop, cadence.backoff_seconds):
                return
            continue
        except Exception:
            log.exception("loop_failed", loop=name)
            health.mark_failed(name)
            raise
        pause = 0.0 if outcome is Iteration.MORE_DUE else cadence.pause_seconds
        if await wait_or_stop(stop, pause):
            return
```

`main.py` owns the process: it loads settings, enters `runtime()`, builds the
list of loops (`iteration=lambda: reattempt_stuck(runtime)`), installs signal
handlers, and awaits `supervise(loops, stop)`. `ProcessHealth` lives in
`supervisor.py` and the runtime never needs it, so there is no import cycle.
For a hybrid service launched through `uvicorn --factory`, the ASGI factory's
lifespan may own this same startup/shutdown sequence instead of `main.py`; use
one process owner, not both. Binding a worker function to the runtime is
wiring; binding an application action hides an entry point and is not allowed
([boundaries.md](boundaries.md#bootstrap)).

- **Failure policy is declared per failure class.** The usual policy, shown
  above: contain the service's unavailable base
  ([errors.md](errors.md#classification-bases)) with backoff, and fail fast on
  everything else, so an outage waits it out and a defect stops the process and
  fails liveness. Containing every `Exception` needs a documented reason.
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

  A loop with no pause (long polling, `MORE_DUE`) still awaits
  `wait_or_stop(stop, 0)`, so an iteration that never suspends cannot starve the
  event loop or miss the stop event.
- Shutdown: set the stop event, wait under `asyncio.timeout(grace)`, cancel what
  remains, then `gather(..., return_exceptions=True)`. Async mechanics are in
  [async-and-lifecycle.md](async-and-lifecycle.md).
  An iteration, including every item of a received batch, must fit the grace
  period, or the worker checks the stop event between items and leaves the
  unstarted ones unsettled for redelivery.

A scheduled batch or CLI that runs once has no supervisor: `main.py` enters the
runtime, calls one worker function or action once, maps the outcome to an exit
code, and exits non-zero on failure.

### Technical jobs

A technical job keeps the process's own data healthy (retention purge,
orphan cleanup, expired-lease sweep) and has no business entry point besides
its loop. It is not an action and gets no `domain/` module, port, or
`application/` file. It is one class in the integration that owns the data
(`db/retention.py`), built once in `runtime()`, whose method runs one pass and
returns whether more work is due:

```python
# db/retention.py
@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationRetention:
    engine: AsyncEngine
    checkpoints: AsyncPostgresSaver
    retention_days: int
    batch_size: int

    async def run_once(self) -> bool:
        """Purge one batch of expired conversations; True when a full batch was purged."""
        ...
```

`main.py` (or the lifespan owner) adds it to the loop list like any worker
(`iteration=lambda: job_iteration(runtime.retention.run_once)`, where
`job_iteration` in `workers/runtime.py` maps the `bool` to `Iteration`). The
job logs its own one-line summary, because no caller interprets it. The
supervisor still owns cadence, failure policy, and shutdown. Replica
coordination uses the lightest rung that holds (`python-sqlmodel-alembic`,
fallback: `../../python-sqlmodel-alembic/references/work-queues.md`, "Choose
the lightest coordination"); a lease with fencing around an idempotent purge is
over-engineering.

It becomes a business operation, with an action and a port, when a trigger
holds today: another entry point runs it (an admin "purge now" route, a
per-user deletion), it chooses business outcomes (statuses, notices), or its
rule must be tested without the database.

## SQS, Kafka, or another broker

A consumer splits into two owners. The **inbox adapter** in `adapters/` owns the
transport: polling and delivery batches, wire-envelope parsing and validation,
trace-context extraction, visibility heartbeat, offset commit, acknowledgement,
and dead-lettering: it sends malformed messages to the DLQ itself (and logs
that decision, being its only handler), and repeatedly failing messages reach
the DLQ through the broker's redrive policy. The **consumer worker** in
`workers/` owns the use case boundary: it calls one action per delivery and maps
the typed outcome to a settlement. There is no root `messaging/`.
The delivery attempt count may cross from the inbox to an action as a plain
retry-policy input when needed; receipt handles, queue URLs, and raw envelopes
still stay in the delivery boundary. A visibility timeout follows the lease rule
in [Uncertain external writes](persistence.md#uncertain-external-writes): it
outlasts the worst case from receive to settlement, or the inbox extends it.

```python
# workers/inbox.py — the inbound contract the worker needs
@dataclass(frozen=True, slots=True, kw_only=True)
class Delivery[T]:
    message: T
    message_id: str  # for log correlation
    token: str  # opaque to workers; only the inbox reads it


@dataclass(frozen=True, slots=True, kw_only=True)
class Retry:
    delay: timedelta


class Ack:
    """Processing finished, whatever the business outcome; delete the message."""


type Settlement = Ack | Retry


class Inbox[T](Protocol):
    async def receive(self) -> Sequence[Delivery[T]]: ...
    async def settle(self, delivery: Delivery[T], settlement: Settlement) -> None: ...
```

```python
# workers/paid_orders.py
async def consume_paid_orders(runtime: WorkerRuntime) -> Iteration:
    deliveries = await runtime.paid_orders.receive()
    for delivery in deliveries:
        outcome = await process_paid_order(
            order=delivery.message,
            store=runtime.shipment_store,
            carrier=runtime.carrier,
            policy=runtime.retry_policy,
        )
        await runtime.paid_orders.settle(delivery, settlement_for(outcome))
    return Iteration.MORE_DUE if deliveries else Iteration.IDLE


def settlement_for(outcome: PaidOrderOutcome) -> Settlement:
    match outcome:
        case OrderShipped() | OrderAlreadySettled() | ShipmentRejected():
            return Ack()  # a rejection is recorded on the order; the message is done
        case RetryScheduled(delay=delay):
            return Retry(delay=delay)
        case _:
            assert_never(outcome)
```

- `adapters/sqs_inbox.py` implements `Inbox[PaidOrder]`. It imports
  `workers/inbox.py` (the contract it implements) and the domain type it
  parses into, nothing else from `workers/`. It never imports an action.
- The action owns business authorization, idempotency and durable admission,
  classification, state transitions, and the retry delay (a domain function
  returned in the outcome). The worker maps outcomes; the inbox applies
  settlements. Neither owns retry policy.
- **Outcome or exception.** When the business declares what a dependency
  failure means for this message (the carrier is down: retry this order later),
  the action catches that port's unavailable error and returns an outcome such
  as `RetryScheduled`. Any failure without such a declared meaning (the database
  or the queue itself is down) propagates: the delivery stays unsettled, the
  broker redelivers it after the visibility timeout, and the supervisor backs
  off.
- A message that makes the action fail with a defect is redelivered and fails
  again. Every consumed queue therefore has a broker redrive policy
  (`maxReceiveCount` to the DLQ) declared with the deployment, or the consumer
  crash-loops on one poison message.
- The inbox's own transport failures are errors declared in `workers/inbox.py`,
  subclassing the unavailable base in `ports/errors.py`, so the supervisor's
  policy covers them.
- Inbound event models from other producers use `extra="ignore"`: a producer
  adding a field must not dead-letter every message. Request bodies the service
  itself defines keep `extra="forbid"`.
- Receipt handles, offsets, topics, and raw envelopes stay in `Delivery.token`
  and the adapter; they never reach `application/`, `domain/`, or `ports/`.
- An action that *publishes* uses an ordinary application port
  (`ports/message_publisher.py`) implemented in `adapters/`.

Start with one flat module (`adapters/sqs_inbox.py`) and promote per
[boundaries.md](boundaries.md#adapters-and-their-placement).

## Hybrid API plus worker

A deployable may expose HTTP endpoints and run workers from one composition
root (`bootstrap/app.py`, `runtime.py`, `supervisor.py`). FastAPI lifespan may
enter `runtime()` and start the supervisor. If API and worker become
independently scaled or deployed, split them into separate services and extract
only stable shared contracts to a library.

## Health and readiness

Health state shared by API routes and the supervisor has one explicit owner,
`ProcessHealth` in `bootstrap/`. `api/` reads it through a narrow `Liveness`
Protocol in `api/dependencies.py` (trigger 4 of
[When a port earns its cost](boundaries.md#when-a-port-earns-its-cost)), and the
same object remembers the last readiness result so probes log only on a
change. The process owner (`main.py` for a worker or the ASGI lifespan for a
hybrid) constructs it once and passes it to the supervisor and API factory
alongside the runtime; the integration runtime does not own it.
Liveness reports process life. Readiness reflects whether the process can accept
useful work: initialized dependencies, compatible schema, healthy progress, and
required external availability. Probe mechanics are in
[async-and-lifecycle.md](async-and-lifecycle.md#health-probes).
For a worker, readiness includes progress: the supervisor records each loop's
last successful iteration, so a stopped loop is distinguishable from an idle
queue. In a hybrid process, a crashed loop fails liveness so the process
restarts, and readiness gates only on what serving requests needs: a stalled
maintenance loop never takes replicas out of rotation.

Liveness, readiness, metrics, and version are **technical endpoints**: they
report on the process itself, are not business entry points, and call no
application action. This is the one statement of that rule:

| Endpoint | Reads | Calls an action? |
| --- | --- | --- |
| Liveness | The supervisor's health state passed to the API factory | No |
| Readiness | A port method on the runtime container (for example `store.ping()`) | No |
| Metrics | Served by the telemetry exporter, not a route handler | No |
| `GET /submissions/{id}` | `get_submission` | Yes, exactly one |

A probe that starts reporting business facts (pending counts, backlog age for an
operator) is a business read and gets an action.
