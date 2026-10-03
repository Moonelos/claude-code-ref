# Internal shared-library structure

Use this reference for a non-deployable Python package under `libs/` or
`packages/`, whether creating it, extracting it from services, or modularizing
an existing member. The `python-repository-setup` skill owns workspace
admission (fallback: `../../python-repository-setup/SKILL.md`, "Before Creating
A Shared Library"), `pyproject.toml`, lockfile, scoped-install, and Docker
mechanics. This reference owns when extraction is permitted or required, the
kind of library it becomes, where each kind may be imported, and the package's
internal modules, public API, errors, lifecycle, and tests.

Every rule below marked **(checked)** is enforced by an import-linter contract
or by `python-service-architecture-audit --library <kind>`
([Enforcement](#enforcement)). The rest is review guidance; **(review)** marks
an importer rule no contract or audit check enforces, so a reviewer confirms it.

## A library is not a smaller service

A library publishes one cohesive capability to its consumers. It has no process
entry point, runtime composition root, deployment settings, background
supervisor, API, or infrastructure lifecycle of its own. Do not copy the
canonical service tree into it:

```text
libs/<distribution-name>/
├── pyproject.toml
├── src/
│   └── <import_package>/
│       ├── __init__.py             # The public API
│       ├── py.typed
│       └── <cohesive modules>
└── tests/
```

No `application/`, `domain/`, `ports/`, `adapters/`, `bootstrap/`, `api/`, or
`config/` folders and no `main.py` **(checked: `bootstrap/` and `main.py`)**. A
package that has a `main.py`, supervises its own process, or ships
independently is a service or CLI and belongs under `services/`, even if other
members import some of its code.

## Extraction triggers

This table is the one decision rule for duplicated code. Apply the first row
that matches; a new library must also pass the admission check in
`python-repository-setup`.

| Situation | Decision |
| --- | --- |
| The code differs in meaning, lifecycle, or dependencies between members | Stays local, even if it looks similar |
| A module is identical (apart from package name) in **three or more** deployables | **Violation**: extract it |
| **Two** copies meant to be the same have diverged semantically | **Violation**: extract, or comment in each copy why the semantics differ |
| **Two** copies enforce one rule both sides must agree on (an authentication or signature check, or a format one member writes and another reads: wire, storage, or embedding parameters), so changing one copy without the other is itself a defect | **Violation**: extract it, into an existing library of the right kind or a new one. Leave consumer-specific policy and error mapping in each member |
| An identical non-business helper in two members, and a library of the right [kind](#library-kinds-and-importers) is already a dependency of both | Move it into that library now; no new library |
| Identical in two deployables, no suitable existing library | May extract when both consumers intend the behavior to remain identical and workspace admission passes; otherwise keep local until a third copy |
| One consumer, but an independently valuable wire contract, schema, or vendor client with a concrete compatibility or dependency-isolation reason | May be a library; state the reason in its `README` or module docstring |
| "We will need it later" | Stays local |

The per-service classification bases in `ports/errors.py`
([errors.md](errors.md#classification-bases)) are prescribed in every service
and exempt from this table; identical copies are expected.

Before finishing any change that adds a helper, grep the other members for
identical function names. An implicit shared storage layout (a prefix one
service writes and another purges) is a contract with one named owner. Apply
the same table to YAML-loading mechanics; there is no separate reuse threshold.
Each service always owns its `Settings` schema. Two consumers permit extraction;
three identical copies require it, and so do two when they must agree. The
test is the cost of divergence, not similarity: if the copies disagreeing
would be a bug, a second copy is already the defect. Permission is not a
requirement to create a new package.

## Library kinds and importers

Every library has exactly **one** kind. A repository may record the scoped
[database-runtime exception](#database-runtime-exception) to extend persistence
contents and importers. The kind decides what it may contain and
which service layers may import it. A package that mixes kinds (a client that
also ships the pure contract types, a models package that also runs queries) is
split by kind, because otherwise pure layers inherit I/O dependencies.

| Kind | Contains | Never contains | Imported in a service by |
| --- | --- | --- | --- |
| **contract** | Enums, value types, wire/JSON document contracts, their validation | I/O, SDKs, ORM, framework imports; only stdlib and `pydantic` **(checked)** | Any layer; `domain/`, `ports/`, and `application/` admit it with `--allow-external` |
| **client** | A typed async client for one external system: its models, errors, auth, transport | Business policy, service port types, retries the consumer also performs | `adapters/` or `genai/` (the class implementing a port), and `bootstrap/` to construct it **(checked by service contract)** |
| **persistence** | SQLModel/SQLAlchemy table metadata and shared column types | Queries, sessions, engines, migrations of one service **(checked: session machinery)** | `db/` and migrations only **(checked by service contract)** |
| **configuration** | File discovery and settings-source construction from explicit caller inputs; may import `pydantic_settings` | Service settings schemas, ambient environment/secret lookup, final settings instantiation, caching, startup policy | `config/` and `bootstrap/` **(checked with workspace)** |
| **observability** | Provider lifecycle, span helpers, propagation, logging processors, redaction | Business span names, metrics, log events | `observability/` and `bootstrap/`; `application/` may import its business-neutral span helpers (`mark_error`) directly rather than through a re-export **(review)** |
| **genai** | Chat-model factories, shared middleware, provider construction policy | Business prompts, task schemas | `genai/`, and `bootstrap/` to construct its connection and configuration input types and its provider client, whose close bootstrap owns (never its model factories, middleware, or task objects, which the service's `genai/` factories build) **(review)** |
| **testing** | Pytest plugins, disposable-infrastructure lifecycle, test-DB guards | Production code | Tests only, as a dev dependency |

Only an observability library imports `opentelemetry.sdk`; every other kind uses
the OpenTelemetry API only **(checked)**. Only a genai library imports
LangChain or LangGraph **(checked)**.

Shared vocabulary (enums, JSON document contracts, value types) lives in a
contract library importable without SQLAlchemy or SQLModel. A persistence
library may import a contract library for column types; the reverse is
forbidden. Observability specifics are owned by `otel-observability`
(fallback: `../../otel-observability/references/setup/shared_library.md`).

Name the library after its capability (`docstore_client`, `workflow_contracts`,
`db_models`, `company_observability`). A distribution or import package named
only `common`, `shared`, `utils`, `helpers`, `core`, or `base` is a
**Violation (checked)**.

## Configuration mechanics

A configuration library may receive a caller-owned settings class, explicit
paths and identities, and caller-created source callables. It may read the
selected files and invoke those sources. It does not create environment or
secret sources itself. Services own their schemas, source precedence,
environment selection and validation, secrets, caching, and startup failures.
File naming and merge conventions are the library's documented behavior, not
universal architecture requirements. Defining a `BaseSettings` subclass in the
library is forbidden **(checked: direct bases)**; indirect inheritance and
instantiating final settings require semantic review.

## Database-runtime exception

A cohesive database runtime with admitted reuse may remain a repository-scoped
exception to `persistence`, rather than introducing a general library kind.
Record it in that member's `pyproject.toml`:

```toml
[tool.service-audit.library-exception]
package = "project_db_runtime"
profile = "database-runtime"
reason = "Two services share the same engine, session and transaction lifecycle."
consumers = ["orchestrator", "worker"]
```

The declaration applies only to the named package audited with `--library
persistence`. Consumers are current service import packages, not future plans;
with `--workspace`, they must exist. It permits engine/session factories, pool
options, generic transaction mechanics, and technical connectivity/schema
readiness SQL. Only `db/` and `bootstrap/` may import it. Business SQL, ORM
business models, migrations, authentication selection, settings/secrets, and
business transaction composition remain service-owned. It receives resolved
inputs and service-defined minimum schema requirements.

The static audit checks the declaration, permits engine/session imports only
for that package, checks consumer placement, and always emits a semantic review
notice. Review technical versus business SQL, configuration, admission, and
resource ownership; the declaration does not establish these by itself. A
factory owns resources it creates. An injected engine is borrowed and must not
be disposed by the runtime; change the API or use a distinct, explicit ownership
transfer operation before disposing an injected engine. Test borrowed cleanup
and owned cleanup separately. Silent ownership transfer is a violation.

## Canonical client library

A client library for an external document API, and the service adapter that
uses it. Every client library has this shape and these rules. The executable
library is [`assets/canonical_library/`](../assets/canonical_library/), with its
independence contract in `pyproject.toml`:

- [`errors.py`](../assets/canonical_library/src/docstore_client/errors.py): the
  `DocstoreError` base and its unavailable (carrying `retry_after`), rejected, and
  protocol subclasses.
- [`models.py`](../assets/canonical_library/src/docstore_client/models.py): the
  `Document` response model, frozen, with `extra="ignore"`.
- [`client.py`](../assets/canonical_library/src/docstore_client/client.py):
  `DocstoreOptions` (the token field has `repr=False`) and `DocstoreClient`, one attempt
  per call over a borrowed `httpx.AsyncClient`. A 404 on the document route
  returns `None`; 400, 409, and 422 raise rejected; transport failures, 401/403,
  every other 4xx, 429, and 5xx raise unavailable
  ([errors.md](errors.md#classification-bases)); an unexpected body raises the
  protocol error. `Retry-After` is read only in its ASCII delay-seconds form
  and capped.
- [`__init__.py`](../assets/canonical_library/src/docstore_client/__init__.py): the
  public API, re-exports and `__all__` only.

The service's port implementation is the only place that sees the library, and
it translates library errors into port errors once
([errors.md](errors.md#translate-once)):

```python
# services/orchestrator/src/orchestrator/adapters/docstore_documents.py
from docstore_client import DocstoreClient, DocstoreProtocolError, DocstoreRejectedError, DocstoreUnavailableError

from orchestrator.domain.documents import DocumentRef
from orchestrator.ports.documents import (
    DocumentSourceRejectedError,
    DocumentSourceUnavailableError,
    SourceDocument,
)


class DocstoreDocumentSource:
    """Implements `DocumentSource` over the document-store API."""

    def __init__(self, *, client: DocstoreClient) -> None:
        self._client = client

    async def fetch(self, *, ref: DocumentRef) -> SourceDocument | None:
        try:
            document = await self._client.find_document(ref.document_id)
        except DocstoreUnavailableError as exc:
            raise DocumentSourceUnavailableError(
                error_code="docstore_unavailable", retry_after=exc.retry_after
            ) from exc
        except (DocstoreRejectedError, DocstoreProtocolError) as exc:
            raise DocumentSourceRejectedError(error_code="docstore_rejected") from exc
        if document is None:
            return None
        return SourceDocument(ref=ref, title=document.title, version=document.version)
```

Bootstrap builds the `httpx.AsyncClient` with explicit timeouts inside its
`AsyncExitStack`, maps settings and secrets to `DocstoreOptions`, and constructs
`DocstoreDocumentSource(client=DocstoreClient(http=http, options=options))`
([async-and-lifecycle.md](async-and-lifecycle.md#resource-acquisition)).
Application actions see only the `DocumentSource` port; `docstore_client` never
appears in `application/`, `domain/`, or `ports/`.

**Do not mirror library types.** A port type that mirrors a technology-neutral
contract-library type one-for-one is not isolation: import it. Mirror only when
the meaning differs, and say how in the docstring.

## Library rules

**Configuration.** A library takes explicit typed values or a frozen options
dataclass it owns, never a Protocol of properties. It never reads environment
variables **(checked)**. Only a configuration library may import
`pydantic_settings` **(checked)**; see [Configuration mechanics](#configuration-mechanics).
Secret fields use
`field(repr=False)`. The service resolves environment, secrets, and YAML and
maps them to the options at bootstrap.

**Errors.** One base error per library (`DocstoreError`), and subclasses that tell
the consumer whether retrying can help (`...UnavailableError` with an optional
`retry_after`, `...RejectedError`) plus a protocol error for malformed
responses. Classify by what is wrong, not by status code
([errors.md](errors.md#classification-bases)): credentials, permissions, and a
wrong route or method are unavailable. Every SDK, transport, and validation
failure is translated once, `from exc`. The library never imports a service's classification bases; the
consumer's adapter maps library errors to its port errors. An expected absence
is a return value (`Document | None`), not an exception.

**Lifecycle.** A library never closes a borrowed resource it was given (`http`,
sessions, SDK clients). Injected resources are borrowed by default; ownership
transfer needs a distinct explicit API, never an implicit constructor convention.
When it must create one itself, it exposes an async
context manager factory (`open_docstore_client(options)`), never `launch()`/`close()`
pairs. No import-time side effects and no mutable module-global state. The
exception is process-singleton SDK state behind idempotent configure/shutdown
functions with a test reset hook.

**Retries.** A client library makes one attempt per call and reports
`retry_after`; the consumer's boundary owns the retry policy
([async-and-lifecycle.md](async-and-lifecycle.md#retry-ownership)). A library
retries internally only when the protocol requires it (token refresh, a
documented idempotent resume); then attempts are configured in its options,
`sleep` and `clock` are injectable, and the consumer does not also retry.

**Logging and telemetry.** Use `logging.getLogger(__name__)` or the service's
structlog convention; never configure logging (`basicConfig`, `dictConfig`,
handlers other than `NullHandler`) **(checked)**. Raise with context instead of
logging and re-raising; the consumer's handling boundary logs once. Only the
OpenTelemetry API, never the SDK, outside an observability library **(checked)**.

**Typing.** Ship `py.typed` **(checked)**. Public signatures are fully
annotated with no `Any`; the library runs the same strict mypy configuration as
services.

**Dependencies.** Never import a deployable's package, settings, bootstrap,
application, domain, or tests **(checked by the independence contract)**.
Declare every runtime dependency you import. Keep optional framework
integrations out of the dependency-light core (a separate module or an extra)
when only some consumers need them. No cycles between libraries; a foundational
library never depends on a higher-level business one.

## Flat first

Begin with the fewest cohesive modules directly under the import package, as
in the canonical client (`client.py`, `models.py`, `errors.py`). Module names
follow the capability's concepts. A small dataclass, exception, or private
helper stays with its owner; do not create one file per class.

Introduce a nested package only when one narrower slice contains several
cohesive modules, changes for a different reason, has its own external
dependency or test setup, owns a distinct public sub-API, or has real naming
pressure. Promote only that
slice (`vendor_client/auth/`, `vendor_client/transport/`). Never pre-create
`interfaces/`, `implementations/`, `factories/`, `plugins/`, `schemas/`, or
`types/` packages **(checked: one-module packages with these names)**, and
never add speculative registries.

## Public API and compatibility

`__init__.py` is the public API: it re-exports the supported entry points and
declares `__all__`, and nothing else **(checked: no definitions in
`__init__.py`)**. Consumers import public names from the package root (or a
documented public subpackage), never `_`-prefixed modules or names **(checked
with `--workspace`)**. A service extends a library type only through documented
public hooks; a subclass that needs `self._private` state means the library
lacks an extension point.

Inside a workspace, all consumers move in the same change as a breaking API
change; there is no versioning or deprecation period. When consumers cannot
migrate atomically, keep an additive API with a removal trigger (see
[modularization.md](modularization.md#migration-sequence)). Do not add
configuration flags to preserve every difference discovered during extraction:
if consumers need materially different semantics, the behavior stays local.

## Tests

The library owns tests under `libs/<library>/tests/`, flat until a second
execution profile exists ([testing.md](testing.md)).

- Library unit tests prove public behavior and every error translation. A
  client library tests against `httpx.MockTransport` (or the SDK's stubber),
  never a live service.
- Library integration tests prove external protocols the library owns.
- Each consumer tests its own adapter's translation of library errors to port
  errors, and fakes its **port**, not the library, in action tests.
- A library does not ship fakes of itself. Test support shared by several
  members is a separate **testing** library.

## Enforcement

- **Independence contract:** every library has an import-linter contract that
  forbids every service package, and also `pydantic_settings` except for a
  configuration library. The TOML is in
  `python-repository-setup` (fallback:
  `../../python-repository-setup/references/pre-commit.md`, "Architecture
  contracts").
- **Importer contracts:** each service's contracts forbid a client library in
  every layer except `adapters/`, `genai/`, and `bootstrap/`, and a persistence
  library everywhere except `db/`. Configuration importers and the scoped
  database-runtime exception follow the allowed layers above. Same file.
- **Static audit:** `python-service-architecture-audit` in library mode
  (`audit_service.py libs/<lib>/src/<pkg> --library <kind> --workspace .`)
  checks the rules marked (checked) above.

## Extraction and modularization sequence

1. Inventory candidate code, imports, current consumers, behavior differences,
   settings, dependencies, tests, and lifecycle ownership.
2. Pick the one [kind](#library-kinds-and-importers); if the code spans kinds,
   plan one library per kind.
3. Define the smallest shared public contract and explicitly list what remains
   service-local.
4. Create the library flat, with `py.typed`, its independence contract, and
   focused tests.
5. Migrate one consumer at a time: replace its copy with an adapter over the
   library, add the importer contract, run the library tests plus that
   consumer's adapter, startup, import, and type checks.
6. Remove duplicated code and transitional imports only after all intended
   consumers have moved.

Preserve behavior during a structure-only extraction. Do not standardize
business semantics merely because the implementations now sit nearby.

## Review questions

The library audit (`python-service-architecture-audit`) answers these after its
static checks.

- Which row of [Extraction triggers](#extraction-triggers) justifies this
  library, and which single kind is it? A library no row justifies is an
  Improvement to inline back into its consumer; code that spans kinds is split
  by kind.
- Is every importer in the service a layer the kind allows, and does each
  consuming service have the importer contract for it?
- Does it avoid service imports, environment reads, logging configuration, and
  resource ownership it cannot dispose? It closes no borrowed resource; review
  any explicit ownership transfer against [Lifecycle](#library-rules).
- Does exactly one layer retry each call?
- Does it translate every failure into its own errors, and does each consumer
  translate those once into port errors?
- Is the public API only what `__init__.py` exports, and do consumers use only
  that?
