# Engine, sessions and transactions

## `engine.py`: builders, never a module-level engine

`engine.py` exposes the engine builder and the session factory builder. It
holds no engine, reads no settings and has no pool literals:

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def build_engine(
    database_url: str,
    *,
    pool_size: int,
    max_overflow: int,
    pool_timeout_seconds: float,
    pool_recycle_seconds: int,
) -> AsyncEngine:
    if pool_size < 1 or max_overflow < 0 or pool_timeout_seconds <= 0:
        raise ValueError(
            f"invalid pool: size={pool_size} overflow={max_overflow} "
            f"timeout={pool_timeout_seconds}"
        )
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
        pool_recycle=pool_recycle_seconds,
        pool_pre_ping=True,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

Bootstrap calls it once per process and registers `dispose` on the exit stack
in the same breath:

```python
# bootstrap/runtime.py
from contextlib import AsyncExitStack

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from myservice.config.secrets import Secrets
from myservice.config.settings import Settings
from myservice.db.engine import build_engine, build_session_factory


def build_database(
    *, settings: Settings, secrets: Secrets, stack: AsyncExitStack
) -> async_sessionmaker[AsyncSession]:
    engine = build_engine(
        secrets.database_dsn.get_secret_value(),  # the DSN carries a password
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout_seconds=settings.db_pool_timeout_seconds,
        pool_recycle_seconds=settings.db_pool_recycle_seconds,
    )
    stack.push_async_callback(engine.dispose)
    return build_session_factory(engine)
```

Acquisition order, cleanup and failure during startup follow
`../../python-service-architecture/references/async-and-lifecycle.md`
(Resource acquisition). Pool sizes are settings and the DSN is a secret
(`python-settings-config`).

- Never call `create_async_engine(...)` per request or per call: each call
  allocates a new pool, and the result looks like a pool-*sizing* problem when
  it is a pool-*count* problem.
- **One-shot processes** (CLIs, probes, diagnostics, migrations) are the
  exception: they build a `NullPool` (or pool-of-1) engine and dispose it in
  `finally`.
- The URL uses an async driver: `postgresql+asyncpg://…` or
  `postgresql+psycopg://…`. Don't mix them within one service.
- Every member that imports `sqlalchemy.ext.asyncio` depends on
  `sqlalchemy[asyncio]`. The extra pulls `greenlet` on every platform; the
  bare package's marker misses macOS `arm64` and fails only on developer Macs.
- Async only, with one exception: the sync `Connection` handed to a
  `run_sync` callback (Alembic `env.py`, `compare_metadata`).

### Pool parameters

An async engine uses `AsyncAdaptedQueuePool`; don't pass `poolclass` for the
app engine.

| Parameter | What it controls | Starting value for settings |
|---|---|---|
| `pool_size` | Persistent connections per process | 5–10 |
| `max_overflow` | Burst connections above `pool_size` | 5–10; **0** when capacity is an intended concurrency cap or the database is external |
| `pool_timeout` | Seconds to wait for a free connection | 30 |
| `pool_recycle` | Reopen connections older than N seconds | 1800 for managed Postgres that drops idle connections |
| `pool_pre_ping` | Liveness check before handing out a connection | always `True` (fixed in the builder) |

**Do the multiplication.** Every replica of every service holds up to
`pool_size + max_overflow` connections. Check `Σ(pool_size + max_overflow)`
across all processes against the database's `max_connections` before growing
any one pool. At scale, a pooler (PgBouncer in transaction mode) is the fix;
see "Per-transaction limits" for the connection settings it requires.

## The session factory

- `build_session_factory` imports no engine; bootstrap passes it in.
- Use SQLAlchemy's `AsyncSession` for the shared factory and every repository.
  For SQLModel instances, call `session.scalars(select(Model))`; for Core
  statements and projections, call `session.execute(...)`. Merely annotating a
  SQLModel session as SQLAlchemy's base class does not change its overridden
  `execute()` method, which emits a deprecation warning.
- `expire_on_commit=False` keeps attributes readable after commit. Without it,
  attribute access triggers an implicit refresh query, which fails in async code.
- A session is not safe for concurrent use. Never share one across tasks, and
  never hold one across unrelated units of work.

## Transactions and the unit of work

The session factory never begins or commits. One owner per operation draws
the transaction.

- **Repositories never call `commit`, `begin` or `rollback`.** They may `flush()`.
- **Exactly one owner draws the transaction.** Which shape an operation uses
  is chosen in
  `../../python-service-architecture/references/persistence.md#choose-the-transaction-owner`;
  the mechanics of each:
  1. **One port call = one transaction.** The class that implements the port
     holds the session factory, opens a transaction per method, and runs its
     queries (or composes repositories) inside it. Never add a separate
     `db/<area>_transactions.py` class that opens the transaction and forwards
     to a same-named repository method (see "No forwarding stores" below).
  2. **The application needs several operations atomically.** A unit of work
     (UoW) is an async context manager that opens the session on enter (not in
     `__init__`) and exposes repositories plus an explicit `commit()`.
     Anything not committed rolls back on exit, including an early return, and
     the session always closes. Never commit implicitly on clean exit.
- **One transaction helper per service** (in a shared DB library once ≥2
  services have it). It opens `sessions.begin()` and translates driver
  failures, so methods don't repeat `try / begin / except SQLAlchemyError`.
  Nothing bypasses it with an ad-hoc `async with factory() as s, s.begin()`.

```python
# db/transactions.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from myservice.ports.errors import DependencyRejectedError, DependencyUnavailableError

# SQLAlchemy wraps driver socket and timeout failures in these. Never add bare
# OSError/TimeoutError around the body: they would relabel non-DB failures in
# the body as DB outages.
_UNAVAILABLE = (OperationalError, InterfaceError, PoolTimeoutError)


def constraint_name(exc: IntegrityError) -> str | None:
    """The violated constraint's name; asyncpg shown (psycopg: `exc.orig.diag.constraint_name`)."""
    cause = getattr(exc.orig, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    return name if isinstance(name, str) else None


@dataclass(frozen=True, slots=True, kw_only=True)
class PortErrors:
    """The calling port's own error types; each store passes its module constant."""

    unavailable: type[DependencyUnavailableError]
    integrity: type[DependencyRejectedError]


@asynccontextmanager
async def _translated(errors: PortErrors) -> AsyncIterator[None]:
    try:
        yield
    except IntegrityError as exc:
        raise errors.integrity(error_code=f"constraint:{constraint_name(exc)}") from exc
    except _UNAVAILABLE as exc:
        raise errors.unavailable(error_code="database_unavailable") from exc


async def _checkout(session: AsyncSession, errors: PortErrors) -> None:
    # asyncpg raises a bare OSError (ConnectionRefusedError, connect timeout)
    # while opening a connection; SQLAlchemy does not wrap it. Catch it only
    # here, around checkout, never around the transaction body.
    try:
        await session.connection()
    except OSError as exc:
        raise errors.unavailable(error_code="database_unreachable") from exc


@asynccontextmanager
async def transaction(
    sessions: async_sessionmaker[AsyncSession], *, errors: PortErrors
) -> AsyncIterator[AsyncSession]:
    async with _translated(errors), sessions() as session, session.begin():
        await _checkout(session, errors)
        yield session


@asynccontextmanager
async def read_transaction(
    sessions: async_sessionmaker[AsyncSession], *, errors: PortErrors
) -> AsyncIterator[AsyncSession]:
    async with transaction(sessions, errors=errors) as session:
        # The connection is already checked out; this is the first statement.
        connection = await session.connection()
        await connection.execute(text("SET TRANSACTION READ ONLY"))
        yield session


@asynccontextmanager
async def unit_of_work_session(
    sessions: async_sessionmaker[AsyncSession], *, errors: PortErrors
) -> AsyncIterator[AsyncSession]:
    """Caller commits explicitly; closing the session rolls back the rest."""
    async with _translated(errors), sessions() as session:
        await _checkout(session, errors)
        yield session
```

Each store declares its port's errors once and passes them on every call, so
two DB ports never share or alias error classes:

```python
# db/claims.py
_ERRORS = PortErrors(unavailable=ClaimStoreUnavailableError, integrity=ClaimStoreIntegrityError)

async with transaction(self._sessions, errors=_ERRORS) as session: ...
```

`constraint_name` is the one helper described under "DB failure contract"; it
lives in `transactions.py` with the other helpers every transaction uses.
On PostgreSQL, verify that `SET TRANSACTION READ ONLY` is the first statement
executed by `read_transaction`, `SHOW transaction_read_only` returns `on`, and
an attempted write is refused. Run the same check for the external connection
path in `external-read-databases.md`; SQLite or a type check cannot establish
these transaction semantics.

A UoW (shape 2); the application calls `await uow.commit()` as its last step:

```python
# db/orders_uow.py
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from myservice.db.orders import OrderRepository
from myservice.db.outbox import OutboxRepository
from myservice.db.transactions import PortErrors, unit_of_work_session
from myservice.ports.orders import OrdersIntegrityError, OrdersUnavailableError

_ERRORS = PortErrors(unavailable=OrdersUnavailableError, integrity=OrdersIntegrityError)


@dataclass(frozen=True, kw_only=True, slots=True)
class OrdersTransaction:
    orders: OrderRepository
    outbox: OutboxRepository
    commit: Callable[[], Awaitable[None]]


@asynccontextmanager
async def orders_unit_of_work(
    *, sessions: async_sessionmaker[AsyncSession]
) -> AsyncIterator[OrdersTransaction]:
    async with unit_of_work_session(sessions, errors=_ERRORS) as session:
        yield OrdersTransaction(
            orders=OrderRepository(session=session),
            outbox=OutboxRepository(session=session),
            commit=session.commit,
        )
```

- **Bootstrap constructs factories**, never repositories: the session factory
  and `partial(orders_unit_of_work, sessions=sessions)`. Repositories are
  built per transaction. Framework dependencies (FastAPI `Depends`) yield a
  UoW from that factory, not a bare session.
- Whether the application sees the UoW through a Protocol is decided in
  `../../python-service-architecture/references/boundaries.md`; never add a
  Protocol per repository class.
- When ≥2 UoWs differ only in their repositories and error type, share a
  private base.
- **No forwarding stores:** a class whose methods only open a session and
  call a same-named repository method is a forwarding layer
  (`../../python-service-architecture/references/boundaries.md#no-forwarding-layers`).
  Nor do callable "repository factory" Protocols add anything.
- Durable "run started" markers get their own committed transaction before
  the work starts. Plain reads may rely on autobegin inside `read_transaction`.
- Repositories don't construct sibling repositories. A query several of them
  need (a fenced ownership read) is a module-level function taking a session.

## DB failure contract

General translate-once and classification rules live in
`../../python-service-architecture/references/errors.md` (Translate once;
Classification bases). The DB-specific parts:

- Every public DB-adapter method returns a port type or raises a port-owned
  error:
  - **Unavailable** (retryable): `OperationalError`, `InterfaceError` and the
    pool `TimeoutError`, which wrap driver connection and timeout failures.
    Never catch bare `OSError`/`TimeoutError` around a transaction body; the
    one exception is connection checkout, where asyncpg raises a bare `OSError`
    that SQLAlchemy does not wrap (`_checkout` above). Cover it with an
    integration test that points the engine at a closed port.
  - **Integrity or corrupt state:** a named error carrying the constraint,
    never `RuntimeError`.
  - Any other `SQLAlchemyError` (`ProgrammingError`, `DataError`) is a defect;
    it propagates unlabelled rather than being reported as Unavailable.
- Translate at the outermost DB boundary, which is the transaction helper
  (UoW exit, or the store method that opens its own session). Code outside
  `db/` never needs `except Exception` to detect a DB failure.
  `CancelledError` passes through untouched.
- **`IntegrityError`:**
  - For idempotent inserts, prefer `INSERT … ON CONFLICT DO NOTHING RETURNING`,
    then select the existing row when nothing came back.
  - When catching, match the **named constraint** and re-raise anything else,
    so a CHECK or NOT NULL violation is never reported as a duplicate. Read
    the name in one `constraint_name(exc)` helper (psycopg:
    `exc.orig.diag.constraint_name`; asyncpg: `exc.orig.__cause__.constraint_name`).
  - Catching inside a transaction that must continue requires a savepoint
    (`session.begin_nested()`); the failed statement aborts the outer
    transaction otherwise.

## Per-transaction limits

- Every query against a database the service doesn't own, and every batch or
  maintenance statement against one it does, runs in an explicit transaction
  that first sets a transaction-local `statement_timeout` (plus
  `lock_timeout` for writes) through a bound parameter.
- Implement it once per DB package, in `db/transactions.py`, with an explicit
  unit, rounding up:

```python
# db/transactions.py (continued)
import math
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

_SET_LOCAL = text("SELECT set_config(:name, :value, true)")


def _milliseconds(value: timedelta) -> str:
    return f"{math.ceil(value / timedelta(milliseconds=1))}ms"


async def apply_transaction_limits(
    conn: AsyncSession | AsyncConnection,
    *,
    statement_timeout: timedelta,
    lock_timeout: timedelta | None = None,
) -> None:
    await conn.execute(
        _SET_LOCAL, {"name": "statement_timeout", "value": _milliseconds(statement_timeout)}
    )
    if lock_timeout is not None:
        await conn.execute(
            _SET_LOCAL, {"name": "lock_timeout", "value": _milliseconds(lock_timeout)}
        )
```

- Databases the service owns get a role-level or engine-level default
  (`ALTER ROLE … SET statement_timeout`, or `connect_args` server settings),
  so no query is unbounded.
- Invariant session settings go in connection options or a connect event, not
  per query: `search_path`, a read-only default, and, behind PgBouncer
  transaction mode, disabled prepared statements.
  - psycopg: `prepare_threshold=None`.
  - asyncpg under SQLAlchemy: `statement_cache_size=0` alone is not enough,
    because the dialect prepares every statement itself. Also set
    `prepared_statement_cache_size=0` and pass a
    `prepared_statement_name_func` that returns unique names, so two clients
    sharing a server connection never collide on asyncpg's sequential names.
    SQLAlchemy's docs also warn that prepared statements accumulate on the
    server connections unless the app engine uses `NullPool` and PgBouncer
    runs `DISCARD` on release; weigh that against the pooled app engine
    above ([asyncpg dialect: Prepared Statement Name with PGBouncer](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#prepared-statement-name-with-pgbouncer)):

    ```python
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }
    ```
