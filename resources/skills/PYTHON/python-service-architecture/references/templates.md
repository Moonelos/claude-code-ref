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
absent by default; the explicit real-clock seam in
[boundaries.md](boundaries.md#nondeterminism) may justify `core/clock.py`, but
does not invite a general `core/` package. For APIs, workers,
consumers, and hybrid processes, use the trees in
[api-and-workers.md](api-and-workers.md).

## Canonical feature

An idempotent submission endpoint: resolve and normalize the selection, then
insert it or return the existing receipt for the same client and normalized
payload. The executable example is
[`assets/canonical_service/`](../assets/canonical_service/); each module shows
one owner:

- [`domain/submissions.py`](../assets/canonical_service/src/my_service/domain/submissions.py): pure rules,
  unit-tested without doubles. `SelectionRequest`, the normalized `Selection`
  (only `normalize` builds one from a request), `SubmissionPolicy`,
  `normalize` (raises `InvalidSelectionError` past the policy limit), and
  `payload_hash`.
- [`ports/submissions.py`](../assets/canonical_service/src/my_service/ports/submissions.py): what the action needs, in
  business terms. The `SubmissionStore` Protocol, its `Receipt` result, and
  its unavailable and integrity errors.
- [`application/submit.py`](../assets/canonical_service/src/my_service/application/submit.py): the real steps;
  imports only `domain/` and `ports/`. It normalizes, hashes, and makes one
  store call.
- [`db/submissions.py`](../assets/canonical_service/src/my_service/db/submissions.py): implements the port directly,
  transaction and queries in one class. A unique `(client_id, payload_hash)`
  constraint decides duplicates; a conflict returns the existing receipt.
- [`api/routers/submissions.py`](../assets/canonical_service/src/my_service/api/routers/submissions.py): HTTP in, one
  action, HTTP out. `client_id` comes from the verified `WriteIdentity`, never
  from the request body.

The shared `transaction` helper takes the calling port's error types
(`_ERRORS = PortErrors(...)`, one module constant per store), so several DB
ports share the mechanics without sharing error classes. It translates known
DB timeout and disconnect failures with `raise ... from exc` and preserves
unknown failures; constraint conflicts the store expects are handled inside it
first. Helper mechanics are owned by `python-sqlmodel-alembic` (fallback:
`../../python-sqlmodel-alembic/references/engine-and-session.md`, "Transactions
and the unit of work"). Test instructions are in the example's
`tests/README.md`.

[`bootstrap/runtime.py`](../assets/canonical_service/src/my_service/bootstrap/runtime.py)
builds `SqlSubmissionStore(sessions=sessions)` and the
`SubmissionPolicy` once and exposes them on the runtime container; `RuntimeDep`
is the one API dependency for it
([api-and-workers.md](api-and-workers.md#fastapi--http-api)).
`InvalidSelectionError` maps to 422 in the API's exception table,
[`api/exception_handlers.py`](../assets/canonical_service/src/my_service/api/exception_handlers.py)
([api-and-workers.md](api-and-workers.md#public-error-mapping)).

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

The canonical feature's `submit_investigation` illustrates this shape. For a concurrency-safe state
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
