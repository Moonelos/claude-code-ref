# Worker pytest examples

Adapt these patterns to the installed worker framework. They do not replace a
production-broker and production-pool smoke when those mechanics are the risk.

## Asyncio worker loop: commit before acknowledge

Both fakes append to one ordered log, so the assertion proves ordering, not
just that each call happened. The worker exposes a public `tick()`.

```python
import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Self

import pytest

from app.workers.inbox import (
    InboxMessage,
    InboxUnitOfWork,
    InboxWorker,
    MessageSource,
    TickOutcome,
)

pytestmark = pytest.mark.asyncio


@dataclass
class EffectLog:
    events: list[str] = field(default_factory=list)


@dataclass
class FakeSource:
    log: EffectLog
    pending: deque[InboxMessage]

    async def receive(self) -> InboxMessage | None:
        return self.pending.popleft() if self.pending else None

    async def ack(self, message_id: str) -> None:
        self.log.events.append(f"ack:{message_id}")


@dataclass
class FakeInboxUnitOfWork:
    log: EffectLog
    fail_commit: bool = False
    _pending: list[InboxMessage] = field(default_factory=list)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self._pending.clear()

    def record(self, message: InboxMessage) -> None:
        self._pending.append(message)

    async def commit(self) -> None:
        if self.fail_commit:
            raise ConnectionError("commit failed")
        self.log.events.extend(f"commit:{m.message_id}" for m in self._pending)
        self._pending.clear()


_source: MessageSource = FakeSource(EffectLog(), deque())
_uow: InboxUnitOfWork = FakeInboxUnitOfWork(EffectLog())


async def test_message_is_acknowledged_only_after_commit() -> None:
    log = EffectLog()
    worker = InboxWorker(
        source=FakeSource(log, deque([InboxMessage("m-1", "hello")])),
        uow_factory=lambda: FakeInboxUnitOfWork(log),
    )

    async with asyncio.timeout(1):
        outcome = await worker.tick()

    assert outcome is TickOutcome.PROCESSED
    assert log.events == ["commit:m-1", "ack:m-1"]


async def test_failed_commit_leaves_message_unacknowledged() -> None:
    log = EffectLog()
    worker = InboxWorker(
        source=FakeSource(log, deque([InboxMessage("m-1", "hello")])),
        uow_factory=lambda: FakeInboxUnitOfWork(log, fail_commit=True),
    )

    async with asyncio.timeout(1):
        outcome = await worker.tick()

    assert outcome is TickOutcome.FAILED
    assert log.events == []
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
