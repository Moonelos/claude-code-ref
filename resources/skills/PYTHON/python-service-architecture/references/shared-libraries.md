# Internal shared-library structure

Use this reference for a non-deployable Python package under `libs/` or
`packages/`, whether creating it, extracting it from services, or modularizing
an existing member. The `python-repository-setup` skill owns workspace
admission (fallback: `../../python-repository-setup/SKILL.md`, "Before Creating
A Shared Library"), `pyproject.toml`, lockfile, scoped-install, and Docker
mechanics. This reference owns when duplication must be extracted, what kind of
library it becomes, where each kind may be imported, and the package's
internal modules, public API, errors, lifecycle, and tests.

Every rule below marked **(checked)** is enforced by an import-linter contract
or by `python-service-architecture-audit --library <kind>`
([Enforcement](#enforcement)). The rest is review guidance.

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
package that has a `main.py`, owns long-running resources, or ships
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
| An identical non-business helper in two members, and a library of the right [kind](#library-kinds-and-importers) is already a dependency of both | Move it into that library now; no new library |
| Identical in two deployables, no suitable existing library | Keep both. New copies match the existing public signatures exactly; extract on the third copy |
| One consumer, but an independently valuable wire contract, schema, or vendor client with a concrete compatibility or dependency-isolation reason | May be a library; state the reason in its `README` or module docstring |
| "We will need it later" | Stays local |

Before finishing any change that adds a helper, grep the other members for
identical function names. An implicit shared storage layout (a prefix one
service writes and another purges) is a contract with one named owner. A YAML
settings loader is extracted only when two or more services copy it verbatim
and the copies have drifted, or a config library already exists. Each service
always owns its `Settings` schema.

## Library kinds and importers

Every library is exactly **one** kind. The kind decides what it may contain and
which service layers may import it. A package that mixes kinds (a client that
also ships the pure contract types, a models package that also runs queries) is
split by kind, because otherwise pure layers inherit I/O dependencies.

| Kind | Contains | Never contains | Imported in a service by |
| --- | --- | --- | --- |
| **contract** | Enums, value types, wire/JSON document contracts, their validation | I/O, SDKs, ORM, framework imports; only stdlib and `pydantic` **(checked)** | Any layer; `domain/`, `ports/`, and `application/` admit it with `--allow-external` |
| **client** | A typed async client for one external system: its models, errors, auth, transport | Business policy, service port types, retries the consumer also performs | `adapters/` or `genai/` (the class implementing a port), and `bootstrap/` to construct it **(checked by service contract)** |
| **persistence** | SQLModel/SQLAlchemy table metadata and shared column types | Queries, sessions, engines, migrations of one service **(checked: session machinery)** | `db/` and migrations only **(checked by service contract)** |
| **observability** | Provider lifecycle, span helpers, propagation, logging processors, redaction | Business span names, metrics, log events | `observability/` and `bootstrap/` |
| **genai** | Chat-model factories, shared middleware, provider construction policy | Business prompts, task schemas | `genai/` only |
| **testing** | Pytest plugins, disposable-infrastructure lifecycle, test-DB guards | Production code | Tests only, as a dev dependency |

Only an observability library imports `opentelemetry.sdk`; every other kind uses
the OpenTelemetry API only **(checked)**. Only a genai library imports
LangChain or LangGraph **(checked)**.

Shared vocabulary (enums, JSON document contracts, value types) lives in a
contract library importable without SQLAlchemy or SQLModel. A persistence
library may import a contract library for column types; the reverse is
forbidden. Observability specifics are owned by `otel-observability`
(fallback: `../../otel-observability/references/setup/shared_library.md`).

Name the library after its capability (`edm_client`, `workflow_contracts`,
`db_models`, `company_observability`). A distribution or import package named
only `common`, `shared`, `utils`, `helpers`, `core`, or `base` is a
**Violation (checked)**.

## Canonical client library

A client library for an external document API, and the service adapter that
uses it. Every client library has this shape and these rules.

```python
# libs/edm-client/src/edm_client/errors.py
from datetime import timedelta


class EdmError(Exception):
    """Base for every failure this library raises."""


class EdmUnavailableError(EdmError):
    """Timeout, connection failure, 429, or 5xx: the same call may succeed later."""

    def __init__(self, message: str, *, retry_after: timedelta | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EdmRejectedError(EdmError):
    """A 4xx other than 404 and 429: repeating the call fails the same way."""


class EdmProtocolError(EdmError):
    """The response did not match the documented contract."""
```

```python
# libs/edm-client/src/edm_client/models.py
from pydantic import BaseModel, ConfigDict


class Document(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    document_id: str
    title: str
    version: int
```

```python
# libs/edm-client/src/edm_client/client.py
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
from pydantic import ValidationError

from edm_client.errors import EdmProtocolError, EdmRejectedError, EdmUnavailableError
from edm_client.models import Document


@dataclass(frozen=True, slots=True, kw_only=True)
class EdmOptions:
    base_url: str
    api_token: str = field(repr=False)


class EdmClient:
    """Async EDM client. One call is one attempt; the caller owns `http` and retries."""

    def __init__(self, *, http: httpx.AsyncClient, options: EdmOptions) -> None:
        self._http = http
        self._options = options

    async def find_document(self, document_id: str) -> Document | None:
        response = await self._get(f"/documents/{document_id}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        try:
            return Document.model_validate_json(response.content)
        except ValidationError as exc:
            raise EdmProtocolError(f"document {document_id}: unexpected body") from exc

    async def _get(self, path: str) -> httpx.Response:
        try:
            response = await self._http.get(
                f"{self._options.base_url}{path}",
                headers={"Authorization": f"Bearer {self._options.api_token}"},
            )
        except httpx.TransportError as exc:
            raise EdmUnavailableError(f"GET {path}: {type(exc).__name__}") from exc
        status = response.status_code
        if status == httpx.codes.TOO_MANY_REQUESTS or response.is_server_error:
            raise EdmUnavailableError(
                f"GET {path}: HTTP {status}", retry_after=_retry_after(response)
            )
        if response.is_client_error and status != httpx.codes.NOT_FOUND:
            raise EdmRejectedError(f"GET {path}: HTTP {status}")
        return response


def _retry_after(response: httpx.Response) -> timedelta | None:
    value = response.headers.get("Retry-After", "")
    return timedelta(seconds=int(value)) if value.isdigit() else None
```

```python
# libs/edm-client/src/edm_client/__init__.py
"""Async client for the EDM document API."""

from edm_client.client import EdmClient, EdmOptions
from edm_client.errors import (
    EdmError,
    EdmProtocolError,
    EdmRejectedError,
    EdmUnavailableError,
)
from edm_client.models import Document

__all__ = [
    "Document",
    "EdmClient",
    "EdmError",
    "EdmOptions",
    "EdmProtocolError",
    "EdmRejectedError",
    "EdmUnavailableError",
]
```

The service's port implementation is the only place that sees the library, and
it translates library errors into port errors once
([errors.md](errors.md#translate-once)):

```python
# services/orchestrator/src/orchestrator/adapters/edm_documents.py
from edm_client import EdmClient, EdmProtocolError, EdmRejectedError, EdmUnavailableError

from orchestrator.domain.documents import DocumentRef
from orchestrator.ports.documents import (
    DocumentSourceRejectedError,
    DocumentSourceUnavailableError,
    SourceDocument,
)


class EdmDocumentSource:
    """Implements `DocumentSource` over the EDM API."""

    def __init__(self, *, client: EdmClient) -> None:
        self._client = client

    async def fetch(self, *, ref: DocumentRef) -> SourceDocument | None:
        try:
            document = await self._client.find_document(ref.document_id)
        except EdmUnavailableError as exc:
            raise DocumentSourceUnavailableError(
                error_code="edm_unavailable", retry_after=exc.retry_after
            ) from exc
        except (EdmRejectedError, EdmProtocolError) as exc:
            raise DocumentSourceRejectedError(error_code="edm_rejected") from exc
        if document is None:
            return None
        return SourceDocument(ref=ref, title=document.title, version=document.version)
```

Bootstrap builds the `httpx.AsyncClient` with explicit timeouts inside its
`AsyncExitStack`, maps settings and secrets to `EdmOptions`, and constructs
`EdmDocumentSource(client=EdmClient(http=http, options=options))`
([async-and-lifecycle.md](async-and-lifecycle.md#resource-acquisition)).
Application actions see only the `DocumentSource` port; `edm_client` never
appears in `application/`, `domain/`, or `ports/`.

**Do not mirror library types.** A port type that mirrors a technology-neutral
contract-library type one-for-one is not isolation: import it. Mirror only when
the meaning differs, and say how in the docstring.

## Library rules

**Configuration.** A library takes explicit typed values or a frozen options
dataclass it owns, never a Protocol of properties. It never reads environment
variables or imports `pydantic_settings` **(checked)**. Secret fields use
`field(repr=False)`. The service resolves environment, secrets, and YAML and
maps them to the options at bootstrap.

**Errors.** One base error per library (`EdmError`), and subclasses that tell
the consumer whether retrying can help (`...UnavailableError` with an optional
`retry_after`, `...RejectedError`) plus a protocol error for malformed
responses. Every SDK, transport, and validation failure is translated once,
`from exc`. The library never imports a service's classification bases; the
consumer's adapter maps library errors to its port errors. An expected absence
is a return value (`Document | None`), not an exception.

**Lifecycle.** A library never closes a resource it was given (`http`,
sessions, SDK clients). When it must create one itself, it exposes an async
context manager factory (`open_edm_client(options)`), never `launch()`/`close()`
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
dependency or test setup, or owns a distinct public sub-API. Promote only that
slice (`vendor_client/auth/`, `vendor_client/transport/`). Never pre-create
`interfaces/`, `implementations/`, `factories/`, `plugins/`, `schemas/`, or
`types/` packages **(checked: one-module packages with these names)**.

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
  forbids every service package and `pydantic_settings`. The TOML is in
  `python-repository-setup` (fallback:
  `../../python-repository-setup/references/pre-commit.md`, "Architecture
  contracts").
- **Importer contracts:** each service's contracts forbid a client library in
  every layer except `adapters/`, `genai/`, and `bootstrap/`, and a persistence
  library everywhere except `db/`. Same file.
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

- Which row of [Extraction triggers](#extraction-triggers) justifies this
  library, and which single kind is it?
- Is every importer in the service a layer the kind allows?
- Does it avoid service imports, environment reads, logging configuration, and
  resource ownership it cannot dispose?
- Does it translate every failure into its own errors, and does each consumer
  translate those once into port errors?
- Is the public API only what `__init__.py` exports, and do consumers use only
  that?
