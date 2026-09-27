# Boundaries and dependency direction

This file is the single home for placement rules. Other references point here.

## The core rule

Hexagonal structure means business logic knows the conversation shape, not the
technology conducting it.

```text
main ──> bootstrap ──> adapters/db/genai ───┐
                    └─> application actions ├──> ports <── domain
API/adapter consumer ─> application actions ┘
```

The composition root is the only ordinary runtime location that knows which
concrete implementation satisfies a port. Adapters, database repositories, and
GenAI implementations import their ports; ports, domain, and application code
never import those outer packages. `api/`, `adapters/`, `db/`, and `genai/` never
import `bootstrap/`: each declares the narrow Protocol it needs (for example
`ApiRuntime`) and bootstrap satisfies it. GenAI tools may import a public
application action they call.

## Flat-first growth across boundaries

Use the fewest cohesive `.py` modules inside every owning boundary. Keep a small
set—roughly three to five related modules—flat until one narrower area has enough
content, independent change, distinct test setup, or naming pressure to justify
a subpackage. The number is a review signal, not a quota.

Do not create separate modules merely for one class, exception, constants group,
schema, or private helper. Conversely, do not combine unrelated responsibilities
into a catch-all to optimize file count. Root boundaries such as `application/`,
`adapters/`, and `genai/` still express ownership even with one module each.
Every module belongs to a layer or capability package; there is no top-level
miscellaneous module. Delete production modules that only tests use, and never
name a production package `fixtures/`.

## When a port earns its cost

`ports/` is not a dump folder for interfaces. Introduce a Protocol only when a
test substitutes it or a second implementation exists today. Pure validation,
formatting, parsing, and in-memory calculation never need ports; put them in
`domain/` or the owning action and test them directly. Nondeterminism (time,
randomness, ids) is injected as typed callables, not ports; see
[Nondeterminism](#nondeterminism).

Root `ports/` holds only contracts that `application/` imports:

- A contract between two implementation boundaries (a GenAI tool that needs a DB
  reader) lives next to its **consumer**.
- A Protocol that only decouples an outer component from one collaborator is
  declared beside that single consumer.
- A private Protocol narrowing a third-party SDK surface for fakes belongs in the
  adapter module; it is legitimate, and it is not a port.
- Application actions depend on sibling actions concretely, not through a
  Protocol.

**Persistence.** A persistence port gives application code a unit-of-work
boundary and a testable contract. Add a repository/UoW Protocol when application
state-transition logic is unit-tested with fakes; skip it for thin CRUD
pass-through. Use the shapes in `python-sqlmodel-alembic` (fallback:
`../../python-sqlmodel-alembic/references/engine-and-session.md`, "Transactions
and the unit of work"), never a Protocol per repository class.

Name a port after the capability its caller requests. `EmailClassifier` permits
rule-based, LLM, hybrid, and remote implementations; `ClassificationModel`
assumes a model.

## Contract ownership

A port owns its success and failure contract: a typed input, a named result, and
errors built on the service's classification bases
([errors.md](errors.md#classification-bases)).

```python
from dataclasses import dataclass
from typing import Protocol

from my_service.domain.errors import DependencyRejectedError, DependencyUnavailableError
from my_service.domain.workbook import BuiltWorkbook


class WorkbookStoreError(Exception):
    """Base for every failure the workbook store reports."""


class WorkbookStoreUnavailableError(WorkbookStoreError, DependencyUnavailableError):
    """Storage timed out or throttled; retry later."""


class WorkbookStoreRejectedError(WorkbookStoreError, DependencyRejectedError):
    """Storage refused the object; retrying will not help."""


@dataclass(frozen=True, kw_only=True)
class StoredWorkbook:
    key: str
    version_id: str


class WorkbookStore(Protocol):
    async def store(self, *, workbook: BuiltWorkbook) -> StoredWorkbook: ...
```

Adapters translate boto3, HTTP, LangChain, Kafka, filesystem, or vendor
exceptions at the boundary ([errors.md](errors.md#translate-once)). Private
integration errors stay below `adapters/` or `genai/`.

Port hygiene:

- signatures never use `Any`, `object`, `Mapping[str, Any]`, raw provider
  responses, or framework method names (`ainvoke`, `astream`);
- return types are named types; a streaming port yields a closed union of typed
  business events;
- ports contain no helpers, I/O, or configuration defaults, declare methods
  rather than collaborator attributes, and do not re-export domain types;
- a required collaborator has no `None` default.

**Do not mirror library types.** A port-owned type that mirrors a
technology-neutral contract-library type one-for-one is not isolation: import
it. Mirror only when the meaning differs, and say how in the docstring. Apply one
decision per library.

## Validate external structure

At a JSON, queue, HTTP, or SDK boundary, verify the shape and types of required
nested fields before building a domain value, and convert malformed input to a
stable boundary error. Never `str(value)` an arbitrary provider value to satisfy a
string contract. Preserve deliberate handling of documented alternate envelopes
and test events.

Pydantic validates at construction only: `model_copy(update=...)` does not
revalidate. Use it only for already-validated values that cannot violate a
cross-field invariant; rebuild with `model_validate` for untrusted input,
arithmetic that may cross bounds, or updates to related fields.

## Centralized ports and adapters

Concrete S3, SQS, Kafka, browser, remote HTTP, or vendor SDK code lives under
root `adapters/`, never inside `application/` or a business-named package. Keep
small adapter sets flat and encode the provider in the filename
(`s3_manual_store.py`, `nats_publisher.py`).

**Adapter promotion** (the single statement of this rule): promote a provider or
technology to a subpackage only when it has multiple cohesive modules,
independent change or lifecycle setup, distinct test infrastructure, or real
naming pressure. Provider identity alone never justifies a folder, and one-file
provider subpackages are not allowed. For a few AWS modules prefer
`adapters/aws/sqs_consumer.py`, `sqs_serialization.py`, `s3_raw_email_store.py`;
promote only the slice that grows (`adapters/aws/sqs/`).

Root `genai/` holds every GenAI implementation and root `db/` all persistence and
SQL, including DDL, bootstrap SQL, and staging loads. HTTP stays in `api/`. There
is no root `messaging/`: broker consumers, clients, serialization,
acknowledgement, and visibility live in `adapters/<broker-or-provider>/`, and
delivery types that never reach application code stay private there.

## Folder responsibilities

### `bootstrap/`

Bootstrap constructs and wires; it returns a typed runtime container. It never
contains business classification, authorization, routing, state transitions,
provider parsing, SQL, or closures that run DB queries or business steps. Each
supervised operation is an application action; readiness calls a port method.

- Use one lifecycle idiom, an `@asynccontextmanager runtime(settings, secrets)`
  owning one `AsyncExitStack`
  ([async-and-lifecycle.md](async-and-lifecycle.md#resource-acquisition)).
- Past ~80 lines, split into `_build_<capability>(settings, resources) ->
  <frozen bundle>` functions of about 40 lines each, at stable resource or
  capability seams. No factory per constructor and no generic registry. A service
  with fewer than ~10 collaborators keeps one flat function. Separate files
  (`runtime.py`, `app.py`, `supervisor.py`) follow distinct lifecycle
  responsibilities, not line count.
- Build each concrete adapter once and share it. A composition function taking
  more than ~6 collaborators takes a container.
- Keep gauge initialization, business validation, run-completion summaries, and
  log projections out of wiring (the latter go in `observability/`).
- The runtime container holds only what the process boundary uses, with no
  fields for tests to inspect.
- Substitute test doubles at **one** seam: pass fakes into the composition
  function, or use keyword parameters defaulting to the production constructors.
  Do not add `factory=`/`hooks=`/`clock=None` to every layer; a factories object
  is typed without `Any` or `Callable[..., X]`.
- Diagnostics and maintenance entry points reuse bootstrap factories instead of
  importing concrete adapters.
- When GenAI prompt, schema, or tools depend on runtime context, bootstrap
  injects static ingredients into an assembler class in `genai/<task>/agent.py`;
  it never defines closures containing GenAI assembly or parsing.

### Constructor contracts

A production class's required collaborators and limits are required keyword
parameters. No `X | None = None` with a built-in fallback, magic-number default,
or "legacy" branch so tests or old callers can omit them. Defaults are allowed
only for effect seams whose default is the real effect, and for genuinely
optional, settings-documented features. Application actions receive capability
implementations; raw SDK or model handles go only into adapter and GenAI
constructors.

### `config/`

Python settings and secret-resolution code; it describes policy and never
instantiates the runtime graph. Everything else about settings, secrets, and YAML
is owned by `python-settings-config` (fallback:
`../../python-settings-config/SKILL.md`).

### `core/`

Keep `core/` absent by default. Create it only for small, stable,
dependency-light primitives already needed across several boundaries, such as
`core/context.py`: immutable tenant, actor, authorization claims, correlation ids,
or allowlisted baggage, created by the API/consumer boundary and passed
explicitly. Errors, constants, settings, and helpers never live here. Mutable
workflow state belongs to the owning action; LangGraph state belongs under
`genai/<task>/graph/`.

### `application/`

Application actions coordinate domain decisions and ports through typed
keyword-only constructor arguments. They never read global settings, environment
variables, app state, or SDK singletons. Business capabilities are organized
*inside* `application/` and `domain/`; there are no root-level peers of the
technical boundaries (`pipeline/`, `use_cases/`, `workflows/`, `operations/`).
Stage or command machinery below `application/` must reflect real execution
semantics. The action shape is in [templates.md](templates.md#use-case-shape).

### Repositories apply decisions

Database repositories are the only ordinary place that executes queries. A
repository method implementing a state transition:

1. reads and locks the rows;
2. maps them to a typed observation (a frozen kw-only dataclass);
3. calls a pure domain decision function, passed as a `Callable` alias;
4. writes the returned decision.

Repositories never choose statuses, error codes, retry delays, human-review
reasons, or user-visible text. Decision invariants go in the decision object's
`__post_init__`. Review a repository method over ~40 lines or with more than two
branches on business state. SQL predicates that *are* the claim eligibility rule
stay in SQL as shared predicates owned by `python-sqlmodel-alembic`.

### Adapters

Adapters translate technology-specific input, output, and failures into the
application's contracts. Queue consumers translate delivery, serialization,
acknowledgement, and visibility and call an application action; they do not
implement classification or state rules.

### `observability/`

Contains logging setup, trace and metric helpers, semantic vocabulary,
propagation, and SDK integrations. It never imports application actions.

Telemetry in application code:

- A use case returns a result or summary (counts, outcome, stop reason); the
  *caller* (supervisor, handler, wrapper) records span attributes, metrics, and
  logs from it.
- Application code may use the service's own `observability/` vocabulary and
  one-line helpers (`with phase_span("x"):`). It never imports `opentelemetry`,
  receives a `Tracer`, builds attribute dicts inline, mutates telemetry
  accumulators, or calls telemetry from each return path.
- An adapter reporting per-attempt facts receives a typed callback
  (`record_outcome: Callable[[Outcome], None]`). Counts discovered inside
  framework callbacks may use a context-local accumulator.
- When telemetry exceeds roughly a fifth of a use case, move it into a decorator
  or context helper. Keep the sequence of outcome decisions (acknowledge, state
  transition) visible; never hide ack or transition order in a generic decorator.
- Observed data never controls business decisions.

LangChain callbacks, tool-tracing middleware, usage parsers, and agent-span
wrappers stay in precise modules such as `observability/genai.py` even when they
import a framework. Generic provider setup stays in `observability/tracing.py`,
which never imports those adapters. A nested GenAI-observability package needs a
large, independently changing surface. Shared provider lifecycle, propagation,
and redaction may move to a library (see
[shared-libraries.md](shared-libraries.md)); service vocabulary stays local.
Instrumentation mechanics are owned by `otel-observability`.

### `diagnostics/` or `maintenance/`

Operator-facing commands and repair workflows, outside runtime business packages,
with the same dependency and authorization boundaries as any entry point.

## Nondeterminism

`domain/`, `application/`, and `db/` never call `datetime.now()`, `time.time()`,
`random.*`, or `uuid4()` directly. Inject keyword-only typed callables whose
defaults are the real effect, with these names everywhere:

```python
clock: Callable[[], datetime]
monotonic: Callable[[], float]
sleep: Callable[[float], Awaitable[None]]
uniform: Callable[[float, float], float]
id_factory: Callable[[], UUID]
```

Never default a clock inside a function body (`now or datetime.now(UTC)`). Lease
and expiry predicates prefer database-owned time via the database-clock helper in
`python-sqlmodel-alembic`.

## Errors and constants follow ownership

Keep errors beside the boundary that gives them meaning; error *design* is in
[errors.md](errors.md). An `errors.py` exists only when an owned taxonomy earns a
file:

- `domain/errors.py`: business invariant and domain-state failures;
- `application/errors.py` or action-local: use-case orchestration failures;
- `ports/<capability>.py`: external failure contracts visible to application code;
- `adapters/<provider>/errors.py`, `genai/<task>/errors.py`: private failures
  translated before crossing a port.

No root, `core/errors.py`, or `common/errors.py` collections, even for a shared
base. The same rule applies to static values; there is no root or
`core/constants.py`:

```text
Business invariant/static value     -> domain/ or its owning module
Use-case-specific invariant         -> application/ or its owning action
Provider-specific static value      -> adapters/<provider>/
LLM/agent-specific static value     -> genai/<task>/
Environment/deployment value        -> config/
```

A model id, queue URL, region, timeout, retention period, or concurrency limit
that can vary by environment is configuration. Constant and enum idioms are in
`python-code-conventions`.

Place other behavior by meaning: retry policy near the boundary that retries,
serialization near the transport or contract, time calculation in the domain or
action that defines time semantics. A genuinely reused helper gets a precisely
named module (`email_normalization.py`). General code-style rules come from
CLAUDE.md.

## External naming

The service name is identical across the `pyproject.toml` distribution, import
package, container/deployment name, and telemetry `service.name`; check all four
when creating or renaming a service.

## Dependency audit

The import and ownership checklist lives only in
`python-service-architecture-audit` (fallback:
`../../python-service-architecture-audit/SKILL.md`, "Dependency audit").
