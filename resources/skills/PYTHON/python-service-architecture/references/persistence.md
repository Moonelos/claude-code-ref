# Atomic persistence and state transitions

Load only for state transitions, concurrent writes, or multi-operation atomicity.
Transaction mechanics are owned by `python-sqlmodel-alembic` (fallback:
`../../python-sqlmodel-alembic/references/engine-and-session.md#transactions-and-the-unit-of-work`).

## Choose the transaction owner

The decision is always a pure function in `domain/`; the only question is who
holds the transaction.

| The operation | Transaction owner | The action's body |
| --- | --- | --- |
| One cohesive persistence operation: read, decide, and write atomically, including an outbox row the decision produces | One port method owns one transaction; the `db/` implementation reads/locks, calls the pure domain decision, and applies it | One call to the port |
| Several persistence operations that must succeed together, which the action interleaves with its own decisions or other ports | A unit-of-work port the action enters; an uncommitted exit rolls back | Observe, call the domain decision, apply, explicitly commit |
| Database state plus a *write* to an external system (payment, shipment, email) | Nobody: a DB transaction cannot cover the remote effect | Commit durable intent first; deliver through an outbox or durable handoff, or reconcile; declare idempotency semantics |
| A *read* from an external system or model, then a database write | Nobody needs one | Call first, then write once in one transaction; no durable intermediate state |

Prefer the first row; use a unit of work only when the action itself must
decide between writes. A one-call action in the first row is correct: it is the
operation's catalog entry. A domain decision stays pure in either shape; a store
may invoke it while holding locks. Do not invent intermediate states: a
classification, lookup, or model call that changes nothing outside the service
is not an effect to protect. Never split
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
When operator action is the named exit, name how an operator discovers the
record (a query, metric, or alert) and the safe action to take; a record parked
with no discoverable path has no exit.
An idempotency key's replay returns the original result, even if mutable
policy (limits, eligibility) changed since; the same key with different
business data is a named conflict, never silently treated as the original.

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
A provider's duplicate-key response (often `409`) on a replay may mean the
effect already happened: classify it from the provider contract, or treat it as
unknown.

For leased delivery, the lease must outlast the worst case from claim to
settlement, including items ahead of it in a sequential batch; otherwise lease
one item at a time, extend the lease, or bound the batch. A fencing token
protects local state but does not prevent a second external call.

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
