# Integration pytest examples

Adapt these patterns to the installed SQLAlchemy version and the actual ownership
of the application session. It applies to framework-neutral backends as well as
FastAPI services.

## SQLAlchemy same-connection transaction fixture

This SQLAlchemy 2.x pattern permits application code using the bound session to
commit while teardown rolls back the outer transaction.

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

Inject this exact session through the application boundary. Do not use this
fixture for a worker or concurrent second connection and assume its commits
roll back; use a unique committed database/schema and explicit cleanup there.

## Async SQLAlchemy same-connection transaction fixture

The asyncio equivalent binds an `AsyncSession` to an `AsyncConnection` inside
an outer transaction. `test_engine` is the session-scoped engine from the core
examples; the fixture's loop scope must match it.

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

The same caveat applies: this isolates only work on this one connection. A
worker, a second connection, or a concurrent claimer needs committed setup in a
unique database, schema, or tenant with explicit cleanup.
