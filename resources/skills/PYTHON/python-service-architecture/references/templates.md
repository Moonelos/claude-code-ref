# Canonical backend template

Use this reference to produce a concrete target tree after applying the
ownership and dependency rules in [boundaries.md](boundaries.md). Omit unused
directories; never add empty packages merely to complete a drawing.

## Application shell

```text
src/<package>/
├── __init__.py
├── main.py                         # Process owner for workers and CLIs; an HTTP-only
│                                   # service has none (`uvicorn --factory <pkg>.bootstrap.app:create_app`)
├── bootstrap/
│   ├── runtime.py                  # Build/dispose implementations; the runtime container
│   ├── app.py                      # ASGI/FastAPI factory, when applicable
│   └── supervisor.py               # Runs workers: tasks, cadence, shutdown, when applicable
├── config/
│   ├── settings.py
│   └── secrets.py
├── api/                            # HTTP entry points, when present
├── workers/                        # Loop and queue-consumer entry points, when present
├── application/                    # Every business action (the catalog)
├── domain/                         # Pure rules and business types (no I/O)
├── ports/                          # One Protocol per I/O capability actions use
├── db/                             # Port implementations over the database
├── adapters/                       # Port implementations over external systems
├── genai/                          # Port implementations over LLMs
├── observability/                  # When the service has telemetry helpers
└── diagnostics/                    # Optional operator diagnostics
```

Create only the directories the service uses. This `config/` is Python settings
code, not the home of YAML baselines; see `python-settings-config`. `core/` is
deliberately absent ([boundaries.md](boundaries.md#core)). For APIs, workers,
consumers, and hybrid processes, use the trees in
[api-and-workers.md](api-and-workers.md).

## Canonical feature

An idempotent submission endpoint: resolve and normalize the selection, then
insert it or return the existing receipt for the same client and normalized
payload. The compact snippets show ownership; the executable example in
[`assets/canonical_service/`](../assets/canonical_service/) contains the
constraint, duplicate handling, and transaction error translation.

```python
# domain/submissions.py — pure rules, unit-tested without doubles
from dataclasses import dataclass


class InvalidSelectionError(Exception):
    """The selection violates submission policy."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectionRequest:
    record_type: str
    max_records: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Selection:
    """A normalized selection; only `normalize` builds one from a request."""

    record_type: str
    max_records: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmissionPolicy:
    default_records: int
    max_records: int


def normalize(request: SelectionRequest, policy: SubmissionPolicy) -> Selection:
    max_records = policy.default_records if request.max_records is None else request.max_records
    if max_records > policy.max_records:
        raise InvalidSelectionError("submission_limit")
    return Selection(record_type=request.record_type.strip().lower(), max_records=max_records)


def payload_hash(selection: Selection) -> str: ...
```

```python
# ports/submissions.py — what the action needs, in business terms
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from my_service.ports.errors import DependencyUnavailableError
from my_service.domain.submissions import Selection


class SubmissionStoreUnavailableError(DependencyUnavailableError):
    """The store could not complete the transaction; retry later."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Receipt:
    request_id: UUID
    replayed: bool


class SubmissionStore(Protocol):
    async def submit(
        self, *, client_id: str, selection: Selection, payload_hash: str
    ) -> Receipt: ...
```

```python
# application/submit.py — the real steps; imports only domain/ and ports/
from my_service.domain.submissions import (
    SelectionRequest,
    SubmissionPolicy,
    normalize,
    payload_hash,
)
from my_service.ports.submissions import Receipt, SubmissionStore


async def submit_investigation(
    *, store: SubmissionStore, policy: SubmissionPolicy, client_id: str, request: SelectionRequest
) -> Receipt:
    selection = normalize(request, policy)
    return await store.submit(
        client_id=client_id, selection=selection, payload_hash=payload_hash(selection)
    )
```

```python
# db/submissions.py — implements the port directly: transaction + queries in one class
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_service.db.transactions import transaction
from my_service.domain.submissions import Selection
from my_service.ports.submissions import Receipt


class SqlSubmissionStore:
    def __init__(self, *, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def submit(self, *, client_id: str, selection: Selection, payload_hash: str) -> Receipt:
        async with transaction(self._sessions, errors=_ERRORS) as session:
            ...  # unique (client_id, payload_hash); handle conflict and return existing receipt
```

```python
# api/routes.py — HTTP in, one action, HTTP out
@router.post("/submissions", status_code=status.HTTP_202_ACCEPTED)
async def submit(body: SubmissionBody, runtime: RuntimeDep, identity: WriteIdentity) -> SubmissionOut:
    receipt = await submit_investigation(
        store=runtime.submission_store,
        policy=runtime.submission_policy,
        client_id=identity.client_id,
        request=body.to_request(),
    )
    return SubmissionOut.from_receipt(receipt)
```

The shared `transaction` helper takes the calling port's error types
(`_ERRORS = PortErrors(...)`, one module constant per store), so several DB
ports share the mechanics without sharing error classes. It translates known
DB timeout and disconnect failures with `raise ... from exc` and preserves
unknown failures; constraint conflicts the store expects are handled inside it
first. Helper mechanics are owned by `python-sqlmodel-alembic` (fallback:
`../../python-sqlmodel-alembic/references/engine-and-session.md`, "Transactions
and the unit of work"). Read the executable example only when implementing
persistence; test instructions are in its `tests/README.md`.

`bootstrap/runtime.py` builds `SqlSubmissionStore(sessions=sessions)` and the
`SubmissionPolicy` once and exposes them on the runtime container; `RuntimeDep`
is the one API dependency for it
([api-and-workers.md](api-and-workers.md#fastapi--http-api)). `InvalidSelectionError` maps to 422 in the API's
exception table ([api-and-workers.md](api-and-workers.md#public-error-mapping)).

Tests: `normalize` and `payload_hash` as plain unit tests; `SqlSubmissionStore`
as an integration test against the real database; the route as a `unit/api/`
test through an in-process client, with `get_runtime` overridden by a runtime of
fakes, asserting only HTTP translation ([testing.md](testing.md#profiles-and-markers)). The action needs
no mock of `SubmissionStore` just to check the hash: that is `payload_hash`'s
unit test. Fake the port only when the action itself has orchestration worth
testing (several ports, ordering, error handling).

## Use-case shape

An action is a plain `async def` named with an imperative verb, taking ports,
policy, and effect seams as keyword-only arguments and returning a typed immutable
result (or `None` when no result is needed).
Use a class only when the action holds state across calls; then it exposes
**one** public `async def execute(*, ...)`.

The submission action above illustrates this shape. For a concurrency-safe state
transition and the UoW alternative, load [persistence.md](persistence.md) only
when the operation needs them.

## Placement test

Use these questions in order when ownership is ambiguous:

| Question | Location |
| --- | --- |
| Is it a business operation an entry point triggers? | `application/` |
| Does it receive a request, message, or timer tick and call one action? | `api/` (HTTP) or `workers/` (loops, consumers) |
| Is it a pure rule, decision, value object, or business noun with no I/O? | `domain/` |
| Is it the action's view of an I/O capability (a Protocol, its result types, its errors)? | `ports/` |
| Does it implement a port over the database? | `db/` |
| Does it implement a port over an ordinary external SDK or system? | `adapters/` |
| Does it contain an LLM, agent, prompt, AI schema, tool, graph, model binding, or behavior-changing AI middleware? | `genai/` |
| Does it exist only to trace, meter, log, or correlate execution? | `observability/` |
| Does it construct or dispose the runtime graph, or run the process's tasks? | `bootstrap/` |

## Tests

Keep tests beside the member, outside its import package. Use
[testing.md](testing.md) as the single authority for the target test tree,
execution profiles, fixture ownership, markers, CI selection, and migration.
