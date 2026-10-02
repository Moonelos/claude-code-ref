# Direct psycopg and `psycopg_pool`

For services that talk to PostgreSQL through psycopg 3 directly, including a
LangGraph `AsyncPostgresSaver` checkpointer. These rules apply unchanged; this
file covers only what differs:

- transaction ownership: [engine-and-session.md](engine-and-session.md#transactions-and-the-unit-of-work);
- the failure contract: [engine-and-session.md](engine-and-session.md#db-failure-contract);
- raw SQL safety: [repositories-and-queries.md](repositories-and-queries.md#raw-sql-safety);
- work queues: [work-queues.md](work-queues.md#work-claiming-and-leases);
- per-transaction limits: [engine-and-session.md](engine-and-session.md#per-transaction-limits).

## Pools

Construct pools **unopened** in bootstrap, from settings, with an explicit
`max_waiting` and acquisition timeout. Register `close` on the exit stack,
then open:

```python
# db/pool.py
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool


def build_pool(
    conninfo: str,
    *,
    min_size: int,
    max_size: int,
    max_waiting: int,
    acquire_timeout_seconds: float,
    behind_pgbouncer: bool,
) -> AsyncConnectionPool[AsyncConnection[DictRow]]:
    kwargs: dict[str, object] = {"autocommit": True, "row_factory": dict_row}
    if behind_pgbouncer:
        kwargs["prepare_threshold"] = None  # None disables prepared statements; 0 prepares all
    return AsyncConnectionPool(
        conninfo,
        open=False,
        min_size=min_size,
        max_size=max_size,
        max_waiting=max_waiting,
        timeout=acquire_timeout_seconds,
        connection_class=AsyncConnection[DictRow],
        kwargs=kwargs,
    )
```

```python
# bootstrap/runtime.py
pool = build_pool(
    secrets.database_dsn.get_secret_value(),
    min_size=settings.db_pool_min_size,
    max_size=settings.db_pool_max_size,
    max_waiting=settings.db_pool_max_waiting,
    acquire_timeout_seconds=settings.db_pool_acquire_timeout_seconds,
    behind_pgbouncer=settings.db_behind_pgbouncer,
)
stack.push_async_callback(pool.close)
await pool.open(wait=True, timeout=settings.db_pool_open_timeout_seconds)
```

Acquisition order and startup failure follow
`../../python-service-architecture/references/async-and-lifecycle.md`
(Resource acquisition).

- The pool-count and multiplication rules in `engine-and-session.md` apply to
  `max_size` exactly as to `pool_size + max_overflow`.
- Invariant session settings (`search_path`, read-only default, role
  defaults) go in the pool's `configure` callback or the conninfo `options`,
  never per query.
- One-shot processes use a single `AsyncConnection.connect(...)` closed in
  `finally`, not a pool.

## Transactions and queries

- `async with pool.connection() as conn, conn.transaction():` is the
  transaction helper's body; the "Transactions and the unit of work" rules in
  `engine-and-session.md` apply to it unchanged.
- Parameters are always bound (`%(name)s`); identifiers and composed SQL use
  `psycopg.sql.SQL` / `sql.Identifier`, never f-strings.
- Map rows into frozen dataclasses with a per-cursor
  `row_factory=class_row(Model)`, not `DictRow` string lookups. The pool's
  `dict_row` default exists for libraries that need it (LangGraph).
- Failure classification: `psycopg.OperationalError`, `psycopg.InterfaceError`
  and `psycopg_pool.PoolTimeout` are Unavailable; `psycopg.errors.IntegrityError`
  subclasses are integrity errors, matched on `exc.diag.constraint_name`.

## LangGraph `AsyncPostgresSaver`

- Pass it the shared pool (`AsyncPostgresSaver(conn=pool)`); it requires
  `autocommit=True` and `dict_row`, which the builder above sets.
- `setup()` runs the library's own schema migrations. That schema has a
  declared owner (the deployable that runs `setup()`), per
  `repo-layout.md`, "Schema ownership and prototype mode". Run it from that
  owner's migration step, not on every service start.
