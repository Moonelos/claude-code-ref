# Boundaries and dependency direction

This file is the single home for placement rules. Other references point here.

## The core rule

Business logic knows the conversation shape, not the technology conducting it.

```text
                    ┌──────────────── hexagon ────────────────┐
api / workers ───>  │ application ──> domain                  │
                    │      └────────> ports (Protocols)       │
                    └───────────────────▲─────────────────────┘
                                        │ implement
                             db/   adapters/   genai/
                                        ▲
                     bootstrap (builds implementations, runs the process)
```

| Boundary | May import (inside the service) | Never imports |
| --- | --- | --- |
| `domain/` | optional `core/` | everything else |
| `ports/` | `domain/`, `core/` | everything else |
| `application/` | `domain/`, `ports/`, sibling actions, `core/`, `observability/` | `api/`, `workers/`, `bootstrap/`, `config/`, `db/`, `adapters/`, `genai/` |
| `api/`, `workers/` | `application/`, `domain/`, `ports/` types, `observability/` | `bootstrap/`, `config/`, `db/`, `adapters/`, `genai/` |
| `db/`, `adapters/`, `genai/` | the ports they implement, `domain/` types they return; a GenAI tool also imports the action it calls and the port *types* that action takes (never their errors, see [ai.md](ai.md#tools-and-mcp)) | `bootstrap/`, `api/`, `workers/`; each other only through a port, or through a Protocol private to the consumer ([ai.md](ai.md#retrieval-and-rag)) |
| `bootstrap/` | everything | — |

- Third-party code: `domain/` and `ports/` use only the standard library,
  `pydantic`, and its typing companions `typing_extensions` and
  `annotated_types`; `application/` may add `structlog` for a recorded fallback
  ([observability](#observability)). Admitted technology-neutral contract
  libraries are allowed in all three.
- Entry points and implementations never import `bootstrap/`. Each declares the
  narrow Protocol it reads (`ApiRuntime`, `WorkerRuntime`) and bootstrap's
  runtime satisfies it. *Why:* bootstrap imports everything, so importing it
  back creates cycles and lets any module reach any implementation.
- Two narrow exceptions: an inbox adapter imports the inbound contract from
  `workers/inbox.py` that it implements, and a GenAI tool imports the one
  public action it calls.
- `bootstrap/` is the only runtime location that knows which concrete class
  satisfies a port.

## Flat-first growth across boundaries

Use the fewest cohesive `.py` modules inside every boundary. Keep roughly three
to five related modules flat until one narrower area has enough content,
independent change, distinct test setup, or naming pressure to justify a
subpackage. The number is a review signal, not a quota.

Flat-first does not mean flat forever. When a capability implementation and
several supporting modules form a cohesive cluster, group them under that
capability (for example, `db/indexing/store.py`, `manifests.py`, and
`publication.py`). For `db/` this is the fixed template in
`python-sqlmodel-alembic`
([The db/ package](../../python-sqlmodel-alembic/references/repo-layout.md#the-db-package)).
Confirm the cluster from responsibilities and imports; keep primitives used across capabilities at the boundary root. Import concrete
implementations from their defining modules, without re-export facades. A file
count alone does not justify a split, and grouping adds no new port or layer.

Do not create a module for one class, exception, constants group, schema, or
private helper; do not combine unrelated responsibilities to save files. A root
boundary exists only when it has content, and every module belongs to one.
Delete production modules that only tests use; never name a production package
`fixtures/`.

## Application ports

Every I/O capability an action uses is a port: database, remote APIs, queues,
storage, identity providers, LLMs. Name it after what the action needs
(`SubmissionStore`, `RecordSource`, `BreakAnalyzer`), not the technology
(`SqlServerRepository`, `BedrockClient`).

- **One port per capability**, not per repository, table, or SDK client. A port
  whose methods span several tables is normal. A capability is **one aggregate
  or lifecycle** (conversations, the runs that answer them, feedback on
  answers), not "everything the main action touches". Signals to split a port
  and its implementation: more than ~12 methods, an implementation over ~400
  lines, or method groups that no single action uses together. Split along
  those method groups into two ports, each implemented directly; never by
  moving the queries into module functions behind a class that wraps each in a
  transaction. Table handles live in `db/models.py` or `db/tables.py`; one `db/`
  capability never imports another
  ([The db/ package](../../python-sqlmodel-alembic/references/repo-layout.md#the-db-package)).
- **Implemented directly** by a class in `db/`, `adapters/`, or `genai/`.
  Additional implementations and behavior-owning decorators are fine; a class
  that only renames the same call is not.
- **Never for pure logic.** A `Protocol` with only `__call__` standing in for a
  domain function is a defect; import the function.
- **Nondeterminism** (time, randomness, ids) is injected as typed callables, not
  ports ([Nondeterminism](#nondeterminism)).
- **Persistence** shapes are in [persistence.md](persistence.md); transaction
  mechanics are owned by `python-sqlmodel-alembic`.

Root `ports/` holds only contracts that `application/` imports. Readiness may
call a `ping()` on a port that actions already use (never a port only readiness
uses). An agent tool that triggers a business operation reaches I/O through an
action, never a port; a read-only tool calls its GenAI task's own collaborators
directly ([ai.md](ai.md#when-a-tool-calls-an-action)). A port whose only
consumer is an action that only an agent tool calls is a GenAI internal, not
an application port. Actions depend on sibling actions concretely, not through
a Protocol.

## When a port earns its cost

A Protocol that is **not** an application port (between two outer components,
or around a collaborator) is introduced only when one of these holds **today**:

1. **A test substitutes it** for something unit tests cannot call.
2. **A second implementation exists.**
3. **A decorator wraps it** (retry, caching, rate limiting) and keeps its
   promises; a caching decorator that returns different results breaks Liskov.
4. **A package may not import the implementation.** A library that calls back
   into a service declares the Protocol; the service implements it. The API's
   and workers' runtime views are this case.

"We may switch provider someday" is not a reason. Place such a Protocol beside
its single consumer, not in `ports/`. A private Protocol narrowing a
third-party SDK surface for fakes belongs in the adapter module.

Membership in `ports/` does not exempt a Protocol from this test. A port with
one implementation, one consuming action, no test double, and no entry point
other than an agent tool is a GenAI internal: move the Protocol beside its
consumer in `genai/<task>/` (trigger 4 usually holds, since `genai/` may not
import `db/`) and delete the action.

**Tests of ports.** Fake a port to test an action's orchestration. A mock whose
assertions only inspect values computed by pure logic is a defect: test the
domain function directly. One action test asserting that the action *applies*
the rule (the stored priority is the floored one) is orchestration, not a
duplicate; testing each branch of the rule through fakes is.

**Persistence ports in tests.** Fake a persistence port only in a test of an
action that orchestrates it with other ports or decisions. A one-call action
and every store method are tested against disposable PostgreSQL, through the
route or the store ([testing.md](testing.md#profiles-and-markers)). Never build
an in-memory fake that reimplements queries, constraints, uniqueness, or
ordering: a test passing against it proves nothing about the database.

## No forwarding layers

Remove intermediaries that only forward a call with the same meaning: handler
classes in bootstrap, `functools.partial` over actions, same-named transaction
coordinators, and modules that only re-export.

Composition is justified when it owns behavior: a transaction scope spanning
several calls, retry or cache policy, or orchestration of sibling actions. A
transaction opened around exactly one call is not owned behavior; the code that
runs the SQL opens it. Keep that responsibility
explicit; do not flatten useful composition to satisfy a hop count.

### Action boundaries: a deliberate cost

Every business operation has one public action, even when its body is one port
call or one domain call; do not invent steps to justify it.

```python
async def delete_submission(*, submission_id: SubmissionId, store: SubmissionStore) -> None:
    await store.delete(submission_id=submission_id)
```

This exception covers public actions only. A private helper or a second name for
the same operation earns nothing from sitting in `application/`.

**Steps shared by several actions.** A step that two actions both run (triage a
ticket, ship one order) is not a catalog entry: put it in a private module
(`application/_shipping.py`) or in the module of the action that owns it, and
never call it from an entry point. An action that *is* a business operation in
its own right stays public, and another action may call it. A result type the
shared step returns and entry points read lives in `domain/` (or the public
action's module), never in the private module; actions reuse those types in
their own outcome unions rather than renaming them. A shared step propagates
dependency outages; each calling action decides whether an outage is an outcome
for it (the consumer retries this message later) or stops its batch (the
sweeper).

## Contract ownership

A port owns its success and failure contract: typed inputs, a named result, and
its own error classes ([errors.md](errors.md#classification-bases)).

```python
from dataclasses import dataclass
from typing import Protocol

from my_service.domain.workbook import BuiltWorkbook
from my_service.ports.errors import DependencyRejectedError, DependencyUnavailableError


class WorkbookStoreUnavailableError(DependencyUnavailableError):
    """Storage timed out or throttled; retry later."""


class WorkbookStoreRejectedError(DependencyRejectedError):
    """Storage refused the object; retrying will not help."""


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredWorkbook:
    key: str
    version_id: str


class WorkbookStore(Protocol):
    async def store(self, *, workbook: BuiltWorkbook) -> StoredWorkbook: ...
```

Add a per-port base (`WorkbookStoreError`) only when a caller catches every
failure of that port as one family. Implementations translate boto3, HTTP,
LangChain, Kafka, filesystem, or vendor exceptions at the boundary
([errors.md](errors.md#translate-once)); private integration errors stay below
`adapters/` or `genai/`.

Port hygiene:

- signatures never use `Any`, `object`, `Mapping[str, Any]`, raw provider
  responses, or framework method names (`ainvoke`, `astream`);
- results are named types; a streaming port yields a closed union of typed
  business events;
- ports contain no helpers, I/O, or configuration defaults, declare methods
  rather than collaborator attributes (UoW accessors follow
  [persistence.md](persistence.md)), and do not re-export domain types;
- a required collaborator has no `None` default;
- every result field is read by production code; a field only tests read is
  removed.

## Validate external structure

At a JSON, queue, HTTP, or SDK boundary, verify the shape and types of required
nested fields before building a domain value, and convert malformed input to a
stable boundary error. Never `str(value)` an arbitrary provider value to satisfy
a string contract. The same applies on the way back in: a stored row that no
longer decodes is an integrity fault. A method returning one record raises its
port's integrity error carrying the row id; a method returning a batch returns
that row as a per-item failure (`Corrupt(row_id=...)` in the result union) so
the rest of the batch proceeds ([errors.md](errors.md#handling-boundaries)). A
corrupt row is almost always our own defect (validation tightened in a deploy):
log it at error and leave the record unchanged for an operator; never move it to
a terminal business state. Two exceptions: a claimed queue row leaves the
claimable set through a technical state `db/` owns, so it is not re-claimed
forever; and a row that is itself the user-visible status settles through the
same domain failure transition as any terminal failure, with an integrity
category, never through a status written outside that transition. When the batch is a cursor page, the cursor advances
past corrupt rows too, so a page with no valid rows still leads to the next.
A value the database or an outbound request cannot accept (a constraint, an
encoding limit) fails as that item's named outcome, never as a process crash
repeated on every redelivery.

When an adapter builds a domain or port value from external data, it uses the
domain's own constructor or predicate rather than a weaker copy in the wire
schema, and translates an invalid response at the adapter boundary so a domain
invariant never escapes as a programming error.

Pydantic validates at construction only: `model_copy(update=...)` does not
revalidate. Rebuild with `model_validate` for untrusted input, arithmetic that
may cross bounds, or updates to related fields.

## Adapters and their placement

Concrete S3, SQS, Kafka, browser, remote HTTP, or vendor SDK code lives under
root `adapters/`, never inside `application/` or a business-named package. Keep
small adapter sets flat with the provider in the filename (`s3_manual_store.py`,
`sqs_inbox.py`).

**Adapter promotion** (the single statement of this rule): promote a provider to
a subpackage only when it has several cohesive modules, independent change or
lifecycle setup, distinct test infrastructure, or real naming pressure. Provider
identity alone never justifies a folder; one-file provider subpackages are not
allowed. Promote only the slice that grows (`adapters/aws/sqs/`).

Adapters translate technology input, output, and failures into their contract.
An inbox adapter (a queue consumer's transport) implements the worker's
`Inbox` contract and never knows which action handles its messages
([api-and-workers.md](api-and-workers.md#sqs-kafka-or-another-broker)).

Root `genai/` holds every GenAI implementation and root `db/` all persistence and
SQL, including DDL and staging loads. There is no root `messaging/`.

## Folder responsibilities

### `bootstrap/`

Bootstrap constructs, wires, and runs the process: `runtime.py` builds the
runtime, `app.py` builds the ASGI app, `supervisor.py` runs workers. It contains
no business classification, authorization, routing, state transitions, provider
parsing, SQL, logging of business results, or closures and `partial`s over
actions. Entry points in `api/` and `workers/` call actions with collaborators
from the runtime.

- One lifecycle idiom: an `@asynccontextmanager runtime(settings, secrets)`
  owning one `AsyncExitStack`
  ([async-and-lifecycle.md](async-and-lifecycle.md#resource-acquisition)).
- `runtime()` stays one flat function while it builds fewer than ~10
  collaborators, however long it is. Past that, split at resource or capability
  seams into `_build_<capability>(settings, resources) -> <frozen bundle>`
  functions. Never one factory per constructor, and no generic registry.
- Build every implementation, including inbox adapters, once in `runtime()`.
  The runtime holds implementations and policies the entry points use, never
  raw SDK clients, application actions, or objects wrapping actions
  (`functools.partial` or a lambda over an action hides an entry point); a
  resource kept only for disposal lives in the exit stack. Binding a *worker
  function* to the runtime (`iteration=lambda: reattempt_stuck(runtime)`) is
  wiring and allowed. Entry points call function actions with fields from the
  runtime (`await sync_tickets(tickets=runtime.tickets, policy=runtime.sync_policy)`).
- Map settings into small frozen policy objects owned by the action or adapter
  that uses them: one named mapping function each, plain values, required
  keyword-only fields. Never pass the whole `Settings` downstream or store
  `Secrets` on `app.state`; a shared library's own config object and test
  factories are exempt.
- Substitute test doubles at **one** seam: pass fakes into the composition
  function, or use keyword parameters defaulting to the production
  constructors. Do not add `factory=`/`hooks=`/`clock=None` to every layer.
- Diagnostics and maintenance entry points reuse bootstrap factories instead of
  importing concrete adapters.
- When GenAI prompts, schemas, or tools depend on runtime context, bootstrap
  injects static ingredients into an assembler class in `genai/<task>/agent.py`.

### Constructor contracts

A production class's required collaborators and limits are required keyword
parameters: no `X | None = None` with a built-in fallback, no magic-number
default, no "legacy" branch so tests or old callers can omit them. Defaults are
allowed only for effect seams whose default is the real effect and for optional,
settings-documented features. Actions receive capability implementations; raw
SDK or model handles go only into adapter and GenAI constructors.

### `config/`

Python settings and secret-resolution code; it describes policy and never
instantiates the runtime graph. This is the complete list of who imports it:

- **The `Settings` and `Secrets` classes:** only `config/` itself,
  `bootstrap/`, `main.py`, and process entry scripts outside the package such
  as Alembic's `env.py`. They load the values once and pass them on; nothing
  else reads settings, secrets, or the environment.
- **A settings-slice type** (`ChatModelSettings`, a `BaseModel` nested in
  `Settings`): also a GenAI or adapter factory, for its signature only; it
  receives the value from bootstrap and never the whole `Settings`
  ([ai.md](ai.md#factories-and-bootstrap-wiring)).
- **Nobody else.** `db/` factories take explicit values
  (`build_engine(dsn, pool_size=...)`). `domain/`, `ports/`, `application/`,
  `api/`, and `workers/` never import `config/`
  ([The core rule](#the-core-rule); checked by the import-linter contracts and
  the audit).

Everything else about settings is owned by `python-settings-config` (fallback:
`../../python-settings-config/SKILL.md`).

### `core/`

Absent by default. Create it only for small, stable, dependency-light
primitives already needed across several boundaries, such as `core/context.py`
(immutable tenant, actor, claims, correlation ids, created by an entry point and
passed explicitly), and `core/clock.py` for the real-clock default
([Nondeterminism](#nondeterminism)). Errors, constants, settings, and helpers
never live here.

### `api/` and `workers/`

The two homes of business entry points. `api/` holds HTTP routes; `workers/`
holds loop iterations and queue consumers
([api-and-workers.md](api-and-workers.md)). Each parses input, resolves request
context, calls one action, and translates the result: an HTTP response, a
delivery settlement, a log line of the returned summary. Neither executes SQL,
initializes clients, invokes LLM SDKs, or branches on business state.

Technical endpoints (liveness, readiness, metrics, version) report on the
process itself and call no action
([api-and-workers.md](api-and-workers.md#health-and-readiness)).

### `application/`

The catalog of everything the service does. An action holds the real sequence
(resolve, validate, decide, persist, trigger effects); input resolution such as
cursor decoding (what position the cursor means) and page-size limits belongs
in the action or `domain/`, not in
the entry point. Actions receive ports and policy as typed keyword-only
arguments and never read settings, environment variables, app state, or SDK
singletons. Business capabilities are organized *inside* `application/` and
`domain/`; there are no root peers such as `pipeline/`, `use_cases/`, or
`workflows/`. The action shape is in [templates.md](templates.md#use-case-shape).

### Repositories apply decisions

Repositories are the only ordinary place that executes queries. A repository
method implementing a state transition reads and locks the rows, maps them to a
typed observation, calls a pure domain decision imported from `domain/`, and
writes the returned decision. The repository imports the decision itself; never
pass it through the port or declare a Protocol for it. The public action stays
in the catalog even though its body is one call.

Repositories never choose business outcomes: statuses (including a new record's
initial status, which a domain constructor sets), persisted or public codes,
retry delays, human-review reasons, or user-visible text. The diagnostic
`error_code` on a port exception is not a business outcome. Decision invariants
go in the decision's `__post_init__` and raise a domain-owned error, never a
bare `ValueError`, so a programming error is never mistaken for an invalid
decision ([domain.md](domain.md#make-invalid-values-impossible-to-build)).
Review a repository method over ~40 lines or with more than two branches on
business state. SQL predicates that *are* an eligibility rule stay in SQL as
shared predicates owned by `python-sqlmodel-alembic`.

### `observability/`

Logging setup, trace and metric helpers, semantic vocabulary, propagation, and
SDK integrations. It never imports actions or entry points.

- An action returns a result or summary (counts, outcome, stop reason); the
  entry point that called it records spans, metrics, and logs from it, except a
  streaming action ([api-and-workers.md](api-and-workers.md#fastapi--http-api),
  Streaming).
  Bootstrap never logs business results.
- Besides a streaming action's terminal outcome, the one log an action writes
  itself is a recorded fallback ([errors.md](errors.md#broad-except-shapes),
  shape 5), because only the `except` that degrades still holds the exception.
  Use the service's logging library directly (`structlog.get_logger()`); do not
  add a module that only re-exports a logger. The degraded result also carries a reason code, so the
  caller can count it.
- Actions may use the service's own `observability/` vocabulary and one-line
  helpers (`with phase_span("x"):`), and the observability library's
  business-neutral span helpers directly; `observability/` never re-exports
  them. They never import `opentelemetry`, receive
  a `Tracer`, build attribute dicts inline, or call telemetry from each return
  path (a streaming action's terminal outcomes excepted). When telemetry
  exceeds roughly a fifth of an action, move it into a decorator or context
  helper, keeping ack and transition order visible.
- An adapter reporting per-attempt facts receives a typed callback
  (`record_outcome: Callable[[Outcome], None]`).
- Observed data never controls business decisions.

GenAI tracing callbacks are placed by [ai.md](ai.md#middleware-and-observability);
instrumentation mechanics are owned by `otel-observability`.

### `diagnostics/` or `maintenance/`

Operator commands and repair workflows, outside runtime business packages, with
the same dependency and authorization boundaries as any entry point.

## Nondeterminism

`domain/`, `application/`, and `db/` never call `datetime.now()`, `time.time()`,
`random.*`, or `uuid4()` directly, including through a model's
`default_factory`. A domain function receives `now` or an id as an argument.
Actions and `db/` classes inject keyword-only typed callables whose defaults are
the real effect, named the same everywhere:

```python
clock: Callable[[], datetime]
monotonic: Callable[[], float]
sleep: Callable[[float], Awaitable[None]]
uniform: Callable[[float, float], float]
id_factory: Callable[[], UUID]
```

The real-effect default is a named function, not a call in the signature (Ruff
`B008`): `clock: Callable[[], datetime] = utc_now`. Define `utc_now()` once in
`core/clock.py`, the one module allowed to read the real clock; `uuid4` and
`random.uniform` are already functions and need no wrapper. Never default a
clock inside a body (`now or datetime.now(UTC)`). Lease and
expiry predicates prefer database-owned time via the database-clock helper in
`python-sqlmodel-alembic`.

## Errors and constants follow ownership

Keep errors beside the boundary that gives them meaning; error *design* is in
[errors.md](errors.md).

- `domain/<concept>.py`: business invariant and state failures, beside the rule
  that raises them; `domain/errors.py` only for failures several concepts share
  (this also avoids import cycles between error modules and the enums they
  carry);
- `application/errors.py` or action-local: use-case orchestration failures;
- `ports/<capability>.py`: that port's failure contract;
- `ports/errors.py`: only the transient/permanent classification bases;
- `adapters/<provider>/errors.py`, `genai/<task>/errors.py`: private failures,
  only when the implementation catches them itself before translating.

No root, `core/errors.py`, or `common/errors.py` collections. The same holds for
static values:

```text
Business invariant/static value     -> domain/ or its owning module
Use-case-specific invariant         -> application/ or its owning action
Provider-specific static value      -> adapters/<provider>/ (settings validators
                                       that need it import it from there)
LLM/agent-specific static value     -> genai/<task>/
Environment/deployment value        -> config/
```

A model id, queue URL, region, timeout, retention period, or concurrency limit
that can vary by environment is configuration. Place other behavior by meaning:
retry policy near the boundary that retries, serialization near the transport,
time calculation in the domain or action that defines it. A genuinely reused
helper gets a precisely named module (`email_normalization.py`). Constant and
enum idioms are in `python-code-conventions`.

## External naming

The service name is identical across the `pyproject.toml` distribution, import
package, container/deployment name, and telemetry `service.name`.

## Dependency audit

The import and ownership checklist lives only in
`python-service-architecture-audit` (fallback:
`../../python-service-architecture-audit/SKILL.md`, "Dependency audit").
