# Work queues, leases and bulk maintenance

For services that use PostgreSQL tables as a work queue, and for scheduled
retention jobs. Examples use the `Job` model from `models-and-base.md`.

## Work claiming and leases

**Claim in one statement.** Select due rows with `FOR UPDATE SKIP LOCKED`,
update them in the same statement and return only the columns the worker needs:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import ColumnElement, and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from myservice.db.transactions import db_now, db_now_plus
from myservice.db.models.job import Job, JobStatus


class WriteOutcome(StrEnum):  # port-owned in real code; shown here for brevity
    APPLIED = "applied"
    STALE = "stale"


@dataclass(frozen=True, kw_only=True, slots=True)
class ClaimedJob:
    job_id: UUID
    run_after: datetime


def job_is_due() -> ColumnElement[bool]:  # shared by claiming and demand counting
    return and_(col(Job.status) == JobStatus.PENDING, col(Job.run_after) <= db_now())


async def claim_jobs(
    session: AsyncSession,
    *,
    worker_id: str,
    lease_token: UUID,
    lease: timedelta,
    limit: int,
) -> list[ClaimedJob]:
    candidates = (
        select(col(Job.id))
        .where(job_is_due())
        .order_by(col(Job.run_after), col(Job.id))
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    claimed = await session.execute(
        update(Job)
        .where(col(Job.id).in_(candidates.scalar_subquery()))
        .values(
            status=JobStatus.RUNNING,
            lease_owner=worker_id,
            lease_token=lease_token,
            lease_until=db_now_plus(lease),
        )
        .returning(col(Job.id), col(Job.run_after))
    )
    jobs = [ClaimedJob(job_id=row.id, run_after=row.run_after) for row in claimed]
    return sorted(jobs, key=lambda job: (job.run_after, job.job_id))  # RETURNING is unordered
```

- The lease token comes from the injected `id_factory`, never `uuid4()` inside
  `db/`.
- Loop per candidate only when a parent must be locked first; lock parents in
  bulk, in sorted order.
- **Every later write is fenced:** filter on the expected state, lease token
  **and** `lease_until > now()`, with `RETURNING id`. "No row" is one typed
  outcome used across the repo:

```python
async def complete_job(
    session: AsyncSession, *, job_id: UUID, lease_token: UUID
) -> WriteOutcome:
    row = (
        await session.execute(
            update(Job)
            .where(
                col(Job.id) == job_id,
                col(Job.status) == JobStatus.RUNNING,
                col(Job.lease_token) == lease_token,
                col(Job.lease_until) > db_now(),
            )
            .values(status=JobStatus.DONE, lease_token=None, lease_until=None)
            .returning(col(Job.id))
        )
    ).first()
    return WriteOutcome.STALE if row is None else WriteOutcome.APPLIED
```

  An exception instead of `STALE` is fine when a stale write is truly
  exceptional; pick one and use it everywhere.
- **State transitions are guarded compare-and-set updates:** one
  `UPDATE … WHERE <current-state guard> RETURNING`, never read-modify-write in
  Python. Guard every column the decision depended on (`IS NULL` for nullable
  ones). After a Core `UPDATE`, re-read with `populate_existing=True` or use
  `RETURNING`.
- **No external I/O while holding locks:** claim → commit → external call →
  fenced write in a new transaction. If holding the lock *is* the point, bound
  the batch and the external timeout, set `idle_in_transaction_session_timeout`,
  and comment the invariant the lock protects.
- **Lock ordering and timeouts:**
  - lock the aggregate root before its children, and multiple rows in PK order;
  - a transaction that waits on `FOR UPDATE` without `SKIP LOCKED` sets a
    local `lock_timeout` (`engine-and-session.md`, "Per-transaction limits");
  - prefer `pg_try_advisory_xact_lock`, including when uniqueness is logical
    rather than enforced by an index. Use a session-level advisory lock only
    when it must outlive a transaction, on a dedicated connection.
- Every claim or scan predicate has a matching partial index
  (`postgresql_where`).
- Code that depends on READ COMMITTED semantics says so in a comment.

## Database clock

Leases, deadlines and due times are computed in SQL with the database clock,
through two helpers in `db/transactions.py` that every service in the repo
writes the same way:

```python
# db/transactions.py (continued)
# Database clock: now() is transaction start, so every row written in one
# transaction shares one timestamp.
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, func


def db_now() -> ColumnElement[datetime]:
    return func.now()


def db_now_plus(delta: timedelta) -> ColumnElement[datetime]:
    return func.now() + delta
```

- Pick `now()` (transaction start) or `statement_timestamp()` (statement
  start), document the choice beside the helpers, and keep it identical across
  services.
- Fetch `SELECT now()` into Python only when application code needs the value
  itself, and never open a transaction just to read the clock. Other code uses
  the injected `clock` callable (`python-service-architecture`).

## Retention and bulk maintenance

Scheduled deletes and updates:

- are bounded per statement and commit per batch:
  `DELETE FROM events WHERE id IN (SELECT id FROM events WHERE <expired> ORDER BY created_at, id LIMIT :n) RETURNING id`;
- set transaction-local timeouts (`apply_transaction_limits`);
- delete children before parents, or rely on `ON DELETE CASCADE`, never both;
- skip rows still referenced by pending work;
- take `pg_try_advisory_lock` when several replicas run the job, and
  invalidate the connection if unlock fails;
- are backed by the partial index the delete predicate implies.
