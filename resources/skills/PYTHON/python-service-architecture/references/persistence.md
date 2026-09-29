# Atomic persistence and state transitions

Load only for state transitions, concurrent writes, or multi-operation atomicity.
Transaction mechanics are owned by `python-sqlmodel-alembic` (fallback:
`../../python-sqlmodel-alembic/references/engine-and-session.md#transactions-and-the-unit-of-work`).

## Choose the transaction owner

| Need | Shape |
| --- | --- |
| One cohesive persistence operation | One port method owns one transaction; the implementation reads/locks, calls a pure domain decision, and applies it |
| Several persistence operations must succeed together | The action enters a UoW port and explicitly commits; uncommitted exit rolls back |
| Database state plus an external write | A DB transaction cannot cover the remote effect; declare outbox/durable handoff or reconciliation and idempotency semantics |
| An external read or model call whose result is then stored | Call first, then write in one transaction; no durable intermediate state is needed |

A domain decision stays pure in either shape. A store may invoke it while holding
locks; the public action remains the operation's catalog entry. Never split
read/decide/write across transactions without an explicit concurrency contract
such as an expected version and conflict outcome. A UoW alone does not prevent
stale reads: choose row locks, conditional writes, or appropriate isolation.
Do not hold database locks while waiting on an external API or model.

**Every durable intermediate state has an exit.** When an operation commits a
state and completes it later (`PENDING` before a carrier call), name in the domain module, beside the state, what moves a record
out of it: the step that completes it, a sweeper that retries it after a
timeout, an operator action, or an expiry. A state that only a crash can leave
behind and nothing can leave is a stuck record. Test the path from a crash after
the first commit to the exit. Make the entry idempotent (a client key or a
natural unique constraint) when a client may retry after a failure.

## One atomic transition

Compact shape; observation mapping and SQL statement details are omitted:

```python
# application/approve_submission.py
async def approve_submission(
    *, submission_id: SubmissionId, actor: Actor, store: SubmissionStore
) -> ApprovalResult:
    return await store.approve(submission_id=submission_id, actor=actor)


# db/submissions.py — method of SqlSubmissionStore
async def approve(self, *, submission_id: SubmissionId, actor: Actor) -> ApprovalResult:
    async with transaction(self._sessions, errors=_ERRORS) as session:
        row = await session.scalar(
            select(SubmissionRow)
            .where(SubmissionRow.request_id == submission_id)
            .with_for_update()
        )
        if row is None:
            raise SubmissionNotFoundError(submission_id)
        decision = approval_decision(observed=to_observation(row), actor=actor)
        row.status = decision.status  # safe: the row lock is held until commit
        return ApprovalResult(submission_id=submission_id, status=decision.status)
```

Without a row lock (a work queue claiming rows), write with a guarded
`UPDATE ... WHERE status = :observed` instead, as `python-sqlmodel-alembic`
prescribes. `approval_decision` owns authorization and legal transitions in `domain/`;
`SubmissionStore.approve` promises atomic application of that decision. The lock
covers the read through commit. This example uses an existing row: concurrent
creation/deduplication needs a unique constraint, not a lock on an absent row.

## Multiple operations in a UoW

The port exposes typed operations and `commit()`, never a raw session. A typed
factory returns an async context manager whose entry creates a fresh transaction.
Use the repository-exposing variant from the SQL skill only when distinct
repository capabilities are actually needed; UoW resource accessors are an
explicit exception to ordinary method-only capability contracts.

```python
# application/admit_submission.py — all work methods share one DB transaction
async def admit_submission(
    *, submission_id: SubmissionId, actor: Actor, work_factory: AdmissionWorkFactory
) -> AdmissionResult:
    async with work_factory() as work:
        observed = await work.observe_for_update(submission_id=submission_id)
        decision = admission_decision(observed=observed, actor=actor)
        await work.apply(decision=decision)
        if decision.event is not None:
            await work.append_outbox(event=decision.event)
        await work.commit()
    return AdmissionResult(submission_id=submission_id, outcome=decision.outcome)
```

The outbox dispatcher owns delivery after commit, with stable event identity and
idempotent consumption. No external call occurs inside this transaction.
Broker acknowledgements stay at the delivery boundary after durable admission;
external writes with uncertain outcomes follow [Uncertain external writes](#uncertain-external-writes).

## Uncertain external writes

For an external write that is not provably safe to replay, distinguish confirmed
success, confirmed rejection, and **unknown**. A timeout or connection loss after
dispatch is unknown, and so is a 2xx whose body cannot be read: the effect
happened, so it is never recorded as a failure; reconcile it. Persist enough identity to reconcile against an
authoritative read or idempotency key before writing again, and test that the
uncertain path never blindly replays. Ordinary retries are fine when the
provider verifies an idempotency key. That guarantee comes from the provider's
documented contract; when the brief does not state it, record it as an
assumption in the port's docstring and in the handoff, never as a fact.

Technical delivery states of an outbox or queue row (`PENDING`, `DELIVERED`,
`FAILED`) belong to `db/`, not `domain/`: the rule that repositories never
choose statuses covers business records, not the queue's own bookkeeping.

## Behavioral verification

Test competing transitions, duplicate requests, conflict outcomes, and rollback
when a later operation fails. For durable handoff, test recovery after commit but
before delivery. Test concurrency against the production database engine;
in-memory fakes and SQLite cannot establish another engine's locking semantics.
[`assets/canonical_service/`](../assets/canonical_service/) contains an
executable duplicate-submission example; load it only when implementing that
path, not during ordinary skill discovery.
