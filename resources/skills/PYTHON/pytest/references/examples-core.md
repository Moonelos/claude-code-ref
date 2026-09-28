# Core pytest examples

These examples demonstrate test shape, not project APIs. Adapt module names,
types, and configuration to the repository. Keep only the applicable pattern.
Shared support types are shown in a member-qualified package, `app_testing`,
under the member's `tests/`; follow the mechanism the repository declares for
making it importable.

## Shared support: unexpected calls and bounded polling

`UnexpectedCall` lets a double reject input without an `assert` that
production error handling could swallow. `wait_until` is the suite's only
polling helper.

```python
# tests/app_testing/errors.py
class UnexpectedCall(BaseException):
    """Raised by a double on input it was not scripted for.

    Subclasses BaseException so production `except Exception` handlers cannot
    swallow it; pytest still reports it as a failure.
    """
```

```python
# tests/app_testing/waiting.py
import asyncio
from collections.abc import Callable


async def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float = 1.0,
    interval: float = 0.005,
) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(interval)
```

## Application behavior through explicit fakes

Prefer a small typed recording fake to a mock graph when application behavior
is the subject. This example proves application-level duplicate-handling
policy, not database durability or concurrent uniqueness.

```python
from dataclasses import dataclass, field
from decimal import Decimal

from app.application.capture_payment import CapturePayment, PaymentRequest
from app.application.ports import PaymentGateway, PaymentStore
from app.domain.payments import PaymentStatus
from app_testing.errors import UnexpectedCall


@dataclass
class InMemoryPayments:
    by_operation: dict[str, PaymentStatus] = field(default_factory=dict)

    def status_for(self, operation_id: str) -> PaymentStatus | None:
        return self.by_operation.get(operation_id)

    def save(self, operation_id: str, status: PaymentStatus) -> None:
        self.by_operation[operation_id] = status


@dataclass
class RecordingGateway:
    charges: list[tuple[str, Decimal]] = field(default_factory=list)
    max_charges: int = 1

    def charge(self, *, idempotency_key: str, amount: Decimal) -> str:
        self.charges.append((idempotency_key, amount))
        if len(self.charges) > self.max_charges:
            raise UnexpectedCall(f"unscripted call {len(self.charges)} to charge")
        return f"provider-payment-{len(self.charges)}"


_store: PaymentStore = InMemoryPayments()
_gateway: PaymentGateway = RecordingGateway()


def test_duplicate_operation_does_not_charge_twice() -> None:
    payments = InMemoryPayments()
    gateway = RecordingGateway()
    capture = CapturePayment(payments=payments, gateway=gateway)
    request = PaymentRequest(operation_id="op-42", amount=Decimal("19.50"))

    capture(request)
    replay = capture(request)

    assert replay.status is PaymentStatus.CAPTURED
    assert gateway.charges == [("op-42", Decimal("19.50"))]
    assert payments.status_for("op-42") is PaymentStatus.CAPTURED
```

The module-level annotated assignments make mypy check each fake against its
port. Add a separate database concurrency test if the real uniqueness guarantee
lives in a constraint, and a provider contract if remote idempotency must be
proved.

## Transactional unit-of-work fake and typed builders

The fake discards uncommitted writes, so a missing `commit()` or a commit on
the failure path is visible in `committed`.

```python
# tests/app_testing/fakes.py
from dataclasses import dataclass, field
from typing import Self

from app.application.ports import OrderUnitOfWork
from app.domain.orders import Order


@dataclass
class FakeOrderUnitOfWork:
    committed: dict[str, Order] = field(default_factory=dict)
    _pending: dict[str, Order] = field(default_factory=dict)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._pending.clear()

    def add(self, order: Order) -> None:
        self._pending[order.order_id] = order

    def commit(self) -> None:
        self.committed.update(self._pending)
        self._pending.clear()


_: OrderUnitOfWork = FakeOrderUnitOfWork()
```

```python
# tests/app_testing/builders.py
from app.domain.orders import OwnedWork


def owned_work(
    *,
    work_id: str = "work-1",
    owner: str = "worker-a",
    attempts: int = 0,
) -> OwnedWork:
    return OwnedWork(work_id=work_id, owner=owner, attempts=attempts)
```

```python
from dataclasses import replace
from decimal import Decimal

import pytest

from app.application.place_order import OrderRejected, PlaceOrder
from app.domain.work import WorkState, next_state
from app_testing.builders import owned_work
from app_testing.fakes import FakeOrderUnitOfWork


def test_rejected_order_leaves_nothing_committed() -> None:
    uow = FakeOrderUnitOfWork()
    place_order = PlaceOrder(uow_factory=lambda: uow)

    with pytest.raises(OrderRejected, match="credit limit"):
        place_order(order_id="order-9", customer_id="customer-3", total=Decimal("-1"))

    assert uow.committed == {}


def test_work_at_attempt_limit_is_dead_lettered() -> None:
    work = replace(owned_work(), attempts=3)

    assert next_state(work, max_attempts=3) is WorkState.DEAD_LETTERED
```

## Parameterize meaningful boundaries

Use IDs that explain each equivalence class. Do not mutate parameter objects.

```python
import pytest

from app.application.retry_policy import FailureKind, classify_failure


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        pytest.param(408, FailureKind.RETRYABLE, id="request-timeout"),
        pytest.param(429, FailureKind.RETRYABLE, id="rate-limited"),
        pytest.param(400, FailureKind.PERMANENT, id="invalid-request"),
        pytest.param(401, FailureKind.PERMANENT, id="bad-credentials"),
        pytest.param(500, FailureKind.RETRYABLE, id="provider-error"),
    ],
)
def test_provider_status_retry_classification(
    status_code: int,
    expected: FailureKind,
) -> None:
    assert classify_failure(status_code) is expected
```

If headers, exception types, or context change the policy, split those behaviors
or include the relevant inputs rather than hiding them in a generic fixture.

## Hypothesis round-trip invariant

Use generated data when a property is stronger than a few examples. Constrain
the strategy to the public domain and retain known regressions explicitly.

```python
from hypothesis import example, given, strategies as st

from app.adapters.events import decode_event, encode_event


event_ids = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=1,
    max_size=64,
)


@example(event_id="incident-escaped-unicode-1", payload={"label": "Δ"})
@given(
    event_id=event_ids,
    payload=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.integers() | st.text(max_size=100) | st.none(),
        max_size=10,
    ),
)
def test_event_encoding_round_trips(event_id: str, payload: dict[str, object]) -> None:
    encoded = encode_event(event_id=event_id, payload=payload)

    assert decode_event(encoded) == {"event_id": event_id, "payload": payload}
```

Keep external I/O out of a high-volume property unless each generated example
has fast, deterministic isolation.

## Async fixtures with pytest-asyncio

A session-scoped engine must live on a session-scoped loop, and the tests that
use it must run on that loop. Mark the module once.

```python
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if url is None:
        pytest.fail("TEST_DATABASE_URL is required for this profile")
    return url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_engine_reaches_the_test_database(test_engine: AsyncEngine) -> None:
    async with test_engine.connect() as connection:
        result = await connection.execute(text("select 1"))
    assert result.scalar_one() == 1
```

With AnyIO instead, use `pytestmark = pytest.mark.anyio`, plain
`@pytest.fixture` async fixtures, and a session-scoped `anyio_backend` fixture
when an async fixture is session-scoped. Apply the test-database guard from
`$python-sqlmodel-alembic` before any destructive setup.
