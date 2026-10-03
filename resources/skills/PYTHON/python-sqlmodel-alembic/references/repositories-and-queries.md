# Repositories and queries

## Where SQL lives

Only the service's `db/` package (and shared DB libraries) imports
`AsyncSession`, `text()`, `select()` or table models for querying.

- Ordinary entity reads and writes go in repositories. A repository class lives
  in the module of the store that uses it (`db/orders.py`, or
  `db/orders/store.py` once promoted); a repository several stores share moves
  to `db/repositories.py`.
- Every other operation sits where `repo-layout.md`, "The db/ package", puts
  it: UoWs and advisory-lock helpers in `transactions.py`, retention passes in
  `retention.py`, the schema guard in `schema.py`; a lease manager or external
  read-only database implements a port and takes its name.
- Application, domain and ports never run SQL. No application port per table
  is required.
- Direct psycopg is valid for PostgreSQL-specific privilege, cursor or policy
  work (`psycopg.md`).

## Repositories

A repository receives its session by keyword and never opens, begins or
commits one (`engine-and-session.md`, "Transactions and the unit of work"):

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from myservice.db.models.user import User


class UserRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.scalars(select(User).where(col(User.email) == email))
        return result.first()
```

- Keep one query style per repository package: `session.scalars(select(...))`
  with `col()` for model-returning code, or Core `execute()` for projections
  and `RETURNING`. Don't mix them method by method.
- Map projections into frozen kw-only dataclasses through named row
  attributes, never `row: Any` indexed by string keys.
- Repositories apply decisions; they don't make them (no choosing statuses,
  retry delays or user-visible text). The read → observe → decide → write
  shape is owned by `../../python-service-architecture/references/boundaries.md`.
  SQL predicates that *are* the eligibility rule for a claim stay in SQL
  (`work-queues.md`).

## Inline queries vs. packaged `.sql`

Keep a query beside its method when filters, joins, locking, projection and
bound parameters read clearly together in SQLAlchemy. That holds especially
for queries that compose, vary, or reuse shared predicates and the database
clock helpers.

Move **long, static** reporting or DBA-reviewed SQL to a packaged `.sql`
resource. Choose by readability and ownership, never by join count. Load it
once through a resource helper, not file I/O at import time. A test loads every
packaged query, and CI runs it against the built wheel installed into a clean
environment (not the source tree), so a wheel that dropped `*.sql` fails:

```python
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib.resources import files

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncSession


@cache
def load_query(name: str) -> TextClause:
    return text(files("myservice.db.queries").joinpath(name).read_text(encoding="utf-8"))


@dataclass(frozen=True, kw_only=True, slots=True)
class MonthlyTotal:
    region: str
    order_count: int


class ReportRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def monthly_totals(
        self, *, month_start: datetime, month_end: datetime
    ) -> list[MonthlyTotal]:
        result = await self._session.execute(
            load_query("monthly_report.sql"),
            {"month_start": month_start, "month_end": month_end},
        )
        return [MonthlyTotal(region=row.region, order_count=row.order_count) for row in result]
```

The `await` is on `execute()`; iterating the returned `Result` is synchronous.

## Async relationships: eager-load explicitly

Lazy-loading a `Relationship()` inside an async session raises
(`MissingGreenlet`) or blocks the loop. Load what the call needs, in the
repository method:

```python
from uuid import UUID

from sqlalchemy.orm import selectinload


async def get_with_reports(self, user_id: UUID) -> User | None:
    # SQLModel types `User.reports` as `list[Report]`, not an ORM attribute.
    reports = selectinload(User.reports)  # type: ignore[arg-type]
    result = await self._session.scalars(
        select(User).where(col(User.id) == user_id).options(reports)
    )
    return result.first()
```

Eager loading is a per-query decision, not a blanket option on the model.

## Raw SQL safety

- Values are always bound, including `IN` lists
  (`bindparam(..., expanding=True)` or `= ANY(:ids)`). Never hand-escape.
- Identifiers go through one validated quoting function in a *public* module
  of the DB package (`psycopg.sql.Identifier`, dialect quoting, or a trusted
  allowlist). DDL identifiers and passwords use `format('%I', …)` /
  `format('%L', …)` server-side.
- An f-string in SQL is allowed only for a module constant or an
  already-validated int, with a comment saying which.
- Composed optional filters use one builder that returns `(clauses, params)`
  and owns all placeholder naming. Use `$n` placeholders only where externally
  authored SQL must round-trip exactly.
- Never execute SQL text taken from outside the repository under an
  application role; untrusted SQL follows `external-read-databases.md`.
- Inside a transaction, never run cleanup SQL in `finally`; rely on rollback
  or `ON COMMIT DROP`.

## Efficient reads and bulk writes

- Select only the columns the result needs, especially for hot claim, scan,
  status and list queries over wide rows (large JSONB or text). Apply the
  page bound in SQL before building objects. A detail read may load everything.
- A page of N items costs a bounded number of queries, not one per item:
  `IN` / `= ANY` lookups into a dict, one query per hop for graph traversal.
- Build counters and indexes once, outside loops. Validate paginated
  accumulation incrementally (a `seen_keys` set), not by rescanning.
- Pagination and "latest per key" are SQL (keyset predicates,
  `DISTINCT ON`), not deserialize-then-filter.
- A bulk state or FK change is one `UPDATE … WHERE id IN (…)` (or
  `= ANY(:ids)`), not a load-modify-flush loop.
- Bulk upsert uses `insert(...).on_conflict_do_update(...)`, chunked at
  `bind_limit // n_columns` rows, where `bind_limit` is the driver's
  bind-parameter limit: 32767 for asyncpg, 65535 for psycopg.
- A projection "rebuilt every run" deletes rows this run didn't produce; an
  upsert alone isn't a rebuild.
- Repository methods accept collections when callers would otherwise loop,
  and return early on empty input.
- A per-row loop inside a transaction is acceptable only when bounded by
  configuration and each row depends on the previous one; state the bound.
- Add an operation-count regression test only for a demonstrated hot path,
  asserting a bound or scaling shape.
