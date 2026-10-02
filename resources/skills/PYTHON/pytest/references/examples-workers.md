# Worker pytest examples

Adapt these patterns to the installed worker framework. They do not replace a
production-broker and production-pool smoke when those mechanics are the risk.

## Consumer worker: settle only after the action commits

The worker is a plain `async def` in `workers/` that takes the runtime view and
returns an `Iteration` (`python-service-architecture`, fallback:
`../../python-service-architecture/references/api-and-workers.md`, "Long-running
worker"). The fake store and the fake inbox append to one ordered log, so the
assertion proves ordering, not just that each call happened. The real action
runs; only its ports and the inbox are fakes.

```python
import asyncio
from collections import deque
from dataclasses import dataclass, field

import pytest

from app.domain.orders import PaidOrder, RetryPolicy
from app.workers.inbox import Ack, Delivery, Retry, Settlement
from app.workers.paid_orders import consume_paid_orders
from app.workers.runtime import Iteration
from app_testing.builders import paid_order

pytestmark = pytest.mark.asyncio


@dataclass
class EffectLog:
    events: list[str] = field(default_factory=list)


@dataclass
class FakeInbox:
    log: EffectLog
    pending: deque[Delivery[PaidOrder]]

    async def receive(self) -> list[Delivery[PaidOrder]]:
        batch = list(self.pending)
        self.pending.clear()
        return batch

    async def settle(self, delivery: Delivery[PaidOrder], settlement: Settlement) -> None:
        self.log.events.append(f"{type(settlement).__name__.lower()}:{delivery.message_id}")


@dataclass
class FakeOrderStore:
    log: EffectLog
    fail_admit: bool = False

    async def admit(self, *, order: PaidOrder) -> None:
        if self.fail_admit:
            raise ConnectionError("database gone")  # an undeclared failure
        self.log.events.append(f"commit:{order.order_id}")


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeRuntime:
    """Satisfies `WorkerRuntime` structurally."""

    paid_orders: FakeInbox
    order_store: FakeOrderStore
    retry_policy: RetryPolicy


def runtime_with(log: EffectLog, *, fail_admit: bool = False) -> FakeRuntime:
    delivery = Delivery(message=paid_order(order_id="o-1"), message_id="m-1", token="t-1")
    return FakeRuntime(
        paid_orders=FakeInbox(log, deque([delivery])),
        order_store=FakeOrderStore(log, fail_admit=fail_admit),
        retry_policy=RetryPolicy(base_seconds=1, max_seconds=60),
    )


async def test_delivery_is_settled_only_after_the_order_commits() -> None:
    log = EffectLog()

    async with asyncio.timeout(1):
        outcome = await consume_paid_orders(runtime_with(log))

    assert outcome is Iteration.MORE_DUE
    assert log.events == ["commit:o-1", "ack:m-1"]


async def test_undeclared_failure_leaves_the_delivery_unsettled() -> None:
    log = EffectLog()

    with pytest.raises(ConnectionError):
        async with asyncio.timeout(1):
            await consume_paid_orders(runtime_with(log, fail_admit=True))

    assert log.events == []  # the broker redelivers after the visibility timeout
```

## Supervisor: bounded drain

Test the generic `run_loop` once, not per worker: a scripted iteration, a stop
event, and a manual sleep. Every await is bounded.

```python
import asyncio

import pytest

from app.bootstrap.supervisor import LoopCadence, ProcessHealth, run_loop
from app.workers.runtime import Iteration

pytestmark = pytest.mark.asyncio


async def test_run_loop_stops_between_iterations() -> None:
    stop = asyncio.Event()
    calls: list[int] = []

    async def iteration() -> Iteration:
        calls.append(len(calls))
        if len(calls) == 2:
            stop.set()
        return Iteration.MORE_DUE

    async with asyncio.timeout(1):
        await run_loop(
            name="orders",
            iteration=iteration,
            cadence=LoopCadence(pause_seconds=60, backoff_seconds=60),
            stop=stop,
            health=ProcessHealth(),
        )

    assert calls == [0, 1]
```

## Database work queue: concurrent claimers

Run against the production dialect with a session factory whose sessions use
separate connections; the same-connection rollback fixture cannot prove row
locking. `seed_ready_job` is a typed row-builder fixture that commits.

```python
import asyncio
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.work_queue import JobQueue

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_concurrent_claimers_never_share_a_row(
    session_factory: async_sessionmaker[AsyncSession],
    seed_ready_job: Callable[[str], Awaitable[None]],
) -> None:
    await seed_ready_job("job-1")
    claimers = [
        JobQueue(session_factory, worker_id=f"worker-{n}") for n in range(2)
    ]

    async with asyncio.timeout(5):
        results = await asyncio.gather(*(queue.claim() for queue in claimers))

    claimed = [claim.job_id for claim in results if claim is not None]
    assert claimed == ["job-1"]
```

Write the stale-owner, lease-expiry, exhaustion, and claim-order cases the same
way, setting lease timestamps through the row builder instead of sleeping.

## Celery task-adapter retry translation

Keep the business action outside the task. Patch it where the task module looks
it up, then assert only the worker-specific translation. This assumes Celery's
default `retry(..., throw=True)` behavior.

This is the third-party-boundary exception to the zero-`unittest.mock` default
in [core-principles.md](core-principles.md#doubles-must-be-correct): `Task.retry`
is Celery control flow with no injectable seam, and the action is a public
module-level function patched in one module, which is tolerated when production
changes are not authorized
([Stop at a missing seam](core-principles.md#stop-at-a-missing-seam)). Both
patches are autospecced. The `exc` identity check is the interaction contract
itself (retry with the original cause), not configured output echoed back. When
the task can receive the action through a seam, replace both patches with a
recording fake.

```python
from unittest.mock import patch

import pytest
from celery.exceptions import Retry

from app.application.delivery import TransientDeliveryError
from app.workers.invoice import deliver_invoice_task


def test_transient_delivery_failure_requests_retry() -> None:
    failure = TransientDeliveryError("provider unavailable")

    with (
        patch(
            "app.workers.invoice.deliver_invoice",
            autospec=True,
            side_effect=failure,
        ),
        patch.object(
            deliver_invoice_task,
            "retry",
            autospec=True,
            side_effect=Retry(),
        ) as retry,
        pytest.raises(Retry),
    ):
        deliver_invoice_task.run("invoice-8")

    retry.assert_called_once()
    assert retry.call_args.kwargs["exc"] is failure
```

Add a terminal-failure case asserting no retry. Test application-owned backoff
calculation as pure policy, and use a real worker test for broker scheduling
instead of sleeping here.

## Bounded worker round trip

This shape applies to Celery's embedded worker fixture when already configured.
It proves more than eager execution but may still differ from the production
broker and pool.

```python
import pytest
from celery.worker import WorkController

from app.workers.events import normalize_event_task


@pytest.mark.worker
def test_event_survives_worker_serialization(celery_worker: WorkController) -> None:
    result = normalize_event_task.delay(
        {"event_id": "event-17", "amount": "10.20"}
    )

    assert result.get(timeout=10) == {
        "event_id": "event-17",
        "amount_minor": 1020,
    }
```

Use a Docker/process smoke with the real broker, backend, and worker pool for
registration, fork safety, acknowledgements, crash/redelivery, and delivery
semantics that the embedded harness cannot prove.
