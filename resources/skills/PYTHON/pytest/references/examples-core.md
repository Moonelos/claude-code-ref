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
    within_seconds: float = 1.0,
    interval_seconds: float = 0.005,
) -> None:
    """Poll `predicate` until it holds; raise TimeoutError after `within_seconds`."""
    async with asyncio.timeout(within_seconds):
        while True:
            if predicate():
                return
            await asyncio.sleep(interval_seconds)
```

The parameter is not named `timeout` (Ruff `ASYNC109`) and the loop body is not
a bare sleep (Ruff `ASYNC110`), so the helper passes the repository Ruff
baseline without `noqa`.

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

## Profile prerequisites: skip locally, fail when required

One mechanism for every infrastructure profile, defined once in the support
package (fixtures call it; `conftest.py` is never imported as a module). A developer without the database gets a visible skip with
the variable to set; a CI job that provisions the profile sets
`REQUIRE_INTEGRATION=1`, and a missing prerequisite then fails instead of
reporting success because everything skipped. There is no per-module
`pytest.skip` and no separate `requires_env` marker.

```python
# tests/app_testing/prerequisites.py
import os

import pytest


def require_env(name: str) -> str:
    """The prerequisite's value; skip locally, fail when the profile is required."""
    value = os.environ.get(name)
    if value:
        return value
    message = f"{name} is not set; this profile needs it"
    if os.environ.get("REQUIRE_INTEGRATION") == "1":
        pytest.fail(message)
    pytest.skip(message)
```

The ordinary fast suite deselects infrastructure profiles
(`addopts = "-m 'not integration and not e2e and not live'"`), so a skip only
appears when someone selects the profile on purpose. The integration CI job
runs `REQUIRE_INTEGRATION=1 pytest -m integration`.

## Async fixtures with pytest-asyncio

A session-scoped engine must live on a session-scoped loop, and the tests that
use it must run on that loop. Mark the module once. The URL comes from the
service's own `INTEGRATION_<DB>_DATABASE_URL`, never `DATABASE_URL`, and the
fixture refuses a non-disposable target before any statement runs; that
contract is owned by `$python-sqlmodel-alembic`
([schema-verification.md](../../python-sqlmodel-alembic/references/schema-verification.md#disposable-test-databases)).

```python
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app_testing.prerequisites import require_env

pytestmark = pytest.mark.asyncio(loop_scope="session")

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@pytest.fixture(scope="session")
def test_database_url() -> str:
    raw = require_env("INTEGRATION_ORDERS_DATABASE_URL")
    url = make_url(raw)
    if url.host not in _LOOPBACK_HOSTS or not (url.database or "").startswith("test_"):
        pytest.fail(f"refusing non-disposable database {url.render_as_string()}")
    return raw


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_database_url)
    try:
        yield engine
    finally:
        await engine.dispose()
```

`render_as_string()` masks the password by default. There is no test that only
proves the engine connects: that would be a framework self-test, and the
guard plus the first repository test using `test_engine` already exercise it.

With AnyIO instead, use `pytestmark = pytest.mark.anyio`, plain
`@pytest.fixture` async fixtures, and a session-scoped `anyio_backend` fixture
when an async fixture is session-scoped.

## SQLAlchemy same-connection transaction fixture

Adapt to the installed SQLAlchemy version and the actual ownership of the
application session; it applies to framework-neutral backends as well as
FastAPI services. The rules and limits of this isolation are in
[integration-boundaries.md](integration-boundaries.md#transaction-isolation-fixture).

The asyncio form binds an `AsyncSession` to an `AsyncConnection` inside an
outer transaction, so application code using the bound session may commit while
teardown rolls back the outer transaction. `test_engine` is the session-scoped
engine above; the fixture's loop scope must match it.

```python
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with test_engine.connect() as connection:
        outer_transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()
```

Synchronous variant, for a sync SQLAlchemy 2.x stack (the same pattern with a
sync `Engine`, `Session`, and explicit `connection.close()`):

```python
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()
```

Inject this exact session through the application boundary. It isolates only
work on this one connection: do not use it for a worker, a second connection, or
a concurrent claimer and assume its commits roll back; use committed setup in a
unique database, schema, or tenant with explicit cleanup there.
