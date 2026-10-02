# FastAPI pytest examples

These are adaptable patterns. Inspect the repository's installed FastAPI,
Starlette, client, AnyIO or pytest-asyncio, SQLAlchemy, and lifespan APIs first.

## Sync client with a runtime of fakes

Routes read one typed runtime through `get_runtime`
(`python-service-architecture`, fallback:
`../../python-service-architecture/references/api-and-workers.md`, "FastAPI /
HTTP API"). A `unit/api/` test overrides that one dependency with a runtime
built from fakes; there is no per-action or per-port provider to override. The
client is not entered as a context manager, so lifespan (which would build the
real runtime) does not run.

```python
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_runtime
from app.bootstrap.app import create_app
from app.domain.orders import OrderPolicy
from app_testing.orders import FakeOrderStore


@dataclass(frozen=True, slots=True, kw_only=True)
class FakeRuntime:
    """Satisfies `ApiRuntime` structurally."""

    order_store: FakeOrderStore
    order_policy: OrderPolicy


@dataclass(frozen=True, slots=True, kw_only=True)
class OrdersApi:
    client: TestClient
    store: FakeOrderStore


@pytest.fixture
def orders_api() -> Iterator[OrdersApi]:
    app = create_app()
    runtime = FakeRuntime(order_store=FakeOrderStore(), order_policy=OrderPolicy(max_quantity=10))
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        yield OrdersApi(client=TestClient(app), store=runtime.order_store)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def test_submit_order_translates_http_to_the_action(orders_api: OrdersApi) -> None:
    response = orders_api.client.post(
        "/orders",
        headers={"Idempotency-Key": "order-op-7"},
        json={"customer_id": "customer-3", "sku": "sku-9", "quantity": 2},
    )

    assert response.status_code == 202
    assert response.json() == {"operation_id": "order-op-7", "status": "accepted"}
    assert orders_api.store.submitted_operation_ids == ["order-op-7"]
```

The route calls the real `submit_order` action with the fake store, so the test
proves HTTP translation and wiring. Keep the business decision matrix in direct
domain and application tests.

## Async client with explicit lifespan

Use this only when the test must await resources on the same loop. This example
pins AnyIO to asyncio because the illustrative SQLAlchemy stack is asyncio-only;
omit or parameterize that fixture when the application deliberately supports
other AnyIO backends. `create_app()` reads the test process's settings, which
point at the disposable database (the variable and guard are in
[examples-core.md](examples-core.md#async-fixtures-with-pytest-asyncio)).

```python
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.app import create_app
from app.db.models import Job
from app.db.vocabulary import JobStatus

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def async_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            yield client


async def test_create_job_commits_visible_state(
    async_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await async_client.post("/jobs", json={"source": "inbox-12"})

    assert response.status_code == 201
    job_id = uuid.UUID(response.json()["id"])
    async with session_factory() as verification_session:
        saved = await verification_session.get(Job, job_id)
    assert saved is not None
    assert saved.status is JobStatus.PENDING
```

The verification session is deliberately fresh. Ensure the app and test
factory point at the same disposable database while using separate sessions.
