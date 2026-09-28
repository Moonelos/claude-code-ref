# Internal shared-library structure

Use this reference for a non-deployable Python package under `libs/` or
`packages/`, whether creating it, extracting it from services, or modularizing
an existing member. The `python-repository-setup` skill owns workspace
admission, `pyproject.toml`, lockfile, scoped-install, and Docker mechanics.
This reference owns the package's internal modules, dependencies, public API,
tests, and migration boundaries.

## A library is not a smaller service

A library publishes a cohesive capability to its consumers. It normally has no
process entry point, runtime composition root, deployment settings, background
supervisor, API, or infrastructure lifecycle of its own. Do not copy the
canonical service tree into it:

```text
libs/<distribution-name>/
├── pyproject.toml
├── src/
│   └── <import_package>/
│       ├── __init__.py
│       └── <cohesive modules>
└── tests/
```

Create `application/`, `domain/`, `ports/`, `adapters/`, `bootstrap/`, `api/`,
or `config/` inside a library only when those words describe real independent
responsibilities in that library. They are not default folders. A package that
has a `main.py`, owns long-running resources, or ships independently may be a
service or CLI and belongs under `services/`, even if other members import some
of its code.

## Confirm the boundary before arranging it

Foldering cannot rescue an unjustified shared abstraction. Before moving code,
identify:

- current consumers and the public behavior each needs;
- the one stable meaning shared by those consumers;
- inputs, outputs, failures, and compatibility obligations;
- external dependencies and whether every consumer should inherit them;
- service-specific policy that must stay with its owner;
- the reason this package can evolve without importing a deployable's private
  implementation.

Ordinarily require demonstrated use by at least two current members. A single-
consumer package can still be valid when it is an independently valuable
protocol/client/schema boundary with a concrete compatibility reason, but do
not split for hypothetical future reuse. Similar syntax with different business
meaning is not reuse.

## Extraction triggers

- A module identical (apart from package name) in **three or more deployables**,
  or **two copies that have diverged semantically**, is a finding that must be
  resolved: extract it, or comment in each copy why the semantics differ.
- An identical non-business helper in two services whose natural library is
  already a dependency of both moves there now; no new library is needed.
- Until extraction, a new copy matches the existing public signatures exactly.
  Before finishing, grep the other members for identical function names.
- An implicit shared storage layout (a prefix one service writes and another
  purges) is a contract with one named owner.
- Code that differs in meaning, lifecycle, or dependencies stays local.
- A YAML settings loader is extracted only when two or more services copy it
  verbatim and the copies have drifted, or a natural shared config library
  already exists. Each service always owns its `Settings` schema.

Prefer a precise capability name such as `edm_client`, `db_models`,
`workflow_contracts`, or `company_observability`. Avoid library distributions
or import packages named only `common`, `shared`, `utils`, `helpers`, `core`, or
`base`.

## Flat first

Begin with the fewest cohesive modules directly under the import package:

```text
src/edm_client/
├── __init__.py
├── client.py
├── auth.py
├── models.py
├── errors.py
└── rate_limit.py
```

This is intentionally less prescriptive than a backend service structure.
Module names follow the capability's own concepts. A small dataclass, exception,
or private helper stays with its owner; do not create one file per class or a
subpackage for every noun.

Introduce a nested package only when one narrower slice:

- contains several cohesive modules;
- changes for a different reason from its siblings;
- has its own external dependency or test setup;
- owns a distinct public sub-API; or
- creates real naming collisions or navigation pressure while flat.

Promote only that slice:

```text
src/vendor_client/
├── __init__.py
├── models.py
├── errors.py
├── auth/
│   ├── credentials.py
│   └── tokens.py
└── transport/
    ├── session.py
    └── retry.py
```

Do not pre-create `interfaces/`, `implementations/`, `factories/`, `plugins/`,
`schemas/`, or `types/` packages for one implementation. A large mixed module
is not preferable to folders; the target is the minimum coherent set, not the
minimum number of files.

## Organize by capability and change ownership

Useful internal shapes depend on what the library publishes:

- A client library may separate authentication, transport, retry/rate limiting,
  wire models, and public errors.
- A schema/model library may group models by stable business capability once a
  flat set becomes difficult to navigate; it must not acquire repositories,
  sessions, migrations, or service orchestration.
- A contract library may group versioned wire contracts, serializers, and
  compatibility validation, while adapters remain with consumers.
- An observability library may own generic providers, spans, propagation,
  resource helpers, structured-logging processors, redaction, and trace/log
  correlation. Business span names, metrics, log events, and outcomes remain
  with each service. Use the `otel-observability` skill for the exact lifecycle and
  logger contract.

Do not mix unrelated horizontal concerns into one organisation library. A
package containing logging, HTTP retries, date helpers, database types, and
business constants has no cohesive owner and will couple every consumer to
unrelated dependencies.

## Dependency direction

An internal library:

- never imports a deployable's source package, settings class, bootstrap,
  application action, domain implementation, or tests;
- accepts configuration as explicit typed values or a concrete frozen dataclass
  it owns (not a Protocol of properties), never by reading environment variables
  or importing `os` or `pydantic_settings` for configuration;
- does not choose deployment policy or construct resources it cannot dispose;
- keeps optional/framework-specific integrations separate from its dependency-
  light core when only some consumers need them;
- avoids cycles between workspace libraries and avoids a foundational package
  depending on a higher-level business package;
- declares every runtime dependency it imports, even if the shared developer
  environment happens to provide it through another member.

The service resolves environment variables, secrets, and YAML through its
settings and maps them to the library's input at bootstrap. A small frozen input
dataclass can live beside its consumer function; neither a separate `config.py`
nor a library `BaseSettings` model is required. Guard independence with an
import-boundary contract test (no `os` configuration reads, no
`pydantic_settings`, no service imports).

Shared vocabulary (enums, JSON document contracts, value types) lives in a module
importable without SQLAlchemy or SQLModel; domain and ports never import the ORM
package root. A schema library may own these contracts but never runs queries or
reads session state.

## Public API and compatibility

Treat the import surface as a contract. Keep `__init__.py` small and deliberate:
re-export the common supported entry points, not every class and internal
helper. Consumers should normally import public package symbols rather than
private modules whose layout may change.

Use leading-underscore modules or documented internal packages when useful, but
do not rely on naming alone: tests and import searches must show that consumers
do not reach into implementation details. Avoid mutable module-global state and
import-time side effects. The exception is process-singleton SDK state behind
idempotent configure/shutdown functions with a test reset hook.

A service extends a library type only through documented public hooks. A
subclass that needs `self._private` state means the library lacks an extension
point; a callback override never swallows exceptions from `super()`.

Do not add configuration flags to preserve every difference discovered during
extraction. If consumers require materially different semantics, keep thin
service-local adapters or leave the behavior local until a stable contract
emerges.

## Tests

The library owns tests under `libs/<library>/tests/`. A small deterministic
suite may stay flat. Once it has distinct execution profiles, apply the profile-
first structure in `testing.md`.

Library unit tests prove public behavior and failures, library integration
tests prove external protocols the library owns, and consumer contract tests
prove each service's adapter still matches the public API. Do not copy library
tests into consumers; consumers keep their own startup, configuration-mapping,
and shutdown tests.

## Extraction and modularization sequence

1. Inventory candidate code, imports, current consumers, behavior differences,
   settings, dependencies, tests, and lifecycle ownership.
2. Define the smallest shared public contract and explicitly list what remains
   service-local.
3. Create or reshape the library around that contract, initially flat, with
   focused tests.
4. Keep compatibility re-exports only when consumers cannot migrate atomically,
   with a removal trigger (see
   [modularization.md](modularization.md#migration-sequence)).
5. Migrate one consumer at a time; run the library tests plus that consumer's
   contract, startup/lifecycle, import, and type checks.
6. Introduce narrower subpackages only where the extracted responsibilities now
   demonstrate independent ownership.
7. Remove duplicated code and transitional imports only after all intended
   consumers have moved.

Preserve behavior during a structure-only extraction. Do not standardize
business semantics merely because the implementations now sit nearby.

## Review questions

- Does the package have current reuse or a concrete compatibility boundary, and
  can its responsibility be described without "and"?
- Does it avoid service-private imports, environment reads, and deployment
  ownership, with a dependency footprint right for every consumer?
- Is the public API intentional, with service policy kept service-local?
- Is migration additive and consumer-by-consumer?
