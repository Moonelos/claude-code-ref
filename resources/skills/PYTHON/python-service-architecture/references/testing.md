# Test suite structure

This file owns test **placement**: layout, profile classification, markers, CI
selection, and the support-package mechanism. Test **design** (doubles,
assertions, async tests, time, flakiness, fixture design) is owned by `pytest`
(fallback: `../../pytest/SKILL.md`). Telemetry tests are owned by
`otel-observability` (fallback: `../../otel-observability/references/testing.md`).

A reader should answer two questions from the path alone:

1. What execution environment and isolation does this test require?
2. Which business capability or technical boundary owns the behavior?

Execution profile is the first axis once a suite has more than one profile;
ownership is the second axis when a profile grows enough to need it.

## Member ownership

Each deployable or internal library owns its tests beside its source
(`services/<service>/tests/`, `libs/<library>/tests/`). A service test may use
public APIs of internal libraries it declares as dependencies. It never imports
another deployable's private package or test helpers. A cross-service system
test lives in an explicitly repository-owned E2E suite or a dedicated test
deployable. Production code never imports `tests`, builders, or fakes.

## Profiles and markers

Use the first matching category; the order makes the folders mutually
exclusive:

1. **`e2e/`** starts the deployable, exercises a complete business flow, or
   crosses multiple real outer boundaries.
2. **`integration/`** exercises at least one concrete outer implementation
   against real disposable infrastructure, a real filesystem or process, or a
   disposable protocol endpoint or emulator, without the whole deployable flow.
3. **`contract/`** verifies a shipped or externally consumed compatibility
   surface without live infrastructure: package exports, shipped configuration
   documents, CLI/deployment entry points, schemas, static migration topology,
   sanitized wire artifacts, architecture fitness rules, or pinned third-party
   framework behavior the service relies on.
4. **`unit/`** runs wholly in process with deterministic collaborators, fakes,
   mock transports, or in-memory framework harnesses.

Classify by what the test executes, not by the package under test, its filename,
or the presence of a mock. A concrete adapter tested with an injected fake SDK
client is a unit test; the same adapter against a real disposable service is an
integration test.

| Behavior under test | Placement |
| --- | --- |
| Domain rule or application action using port fakes | `unit/domain/`, `unit/application/` |
| API router through an in-process client with outer ports replaced | `unit/api/` |
| Worker function or consumer with a fake runtime view and a fake inbox | `unit/workers/` |
| Bootstrap construction and lifecycle with injected constructors | `unit/bootstrap/` |
| Concrete adapter or GenAI capability with a fake SDK or model handle | `unit/adapters/`, `unit/genai/` |
| Settings model validation (types, cross-field rules) | `unit/config/` |
| Repository queries against disposable PostgreSQL | `integration/db/` |
| Broker, object store, browser, or filesystem boundary against a real local implementation | `integration/adapters/` |
| Alembic upgrade/downgrade against a database | `integration/migrations/` |
| Shipped YAML baselines and `.env.example` parse and match the settings model | `contract/config/` |
| Static revision chain, package exports, Docker or CLI entry point | `contract/` under the matching owner |
| Architecture fitness: import direction, forbidden packages, library independence | `contract/architecture/` |
| Third-party framework behavior the service depends on, pinned to locked versions | `contract/framework/` |
| Whole local workflow from process boundary through multiple real components | `e2e/` |

A test reaching a shared staging system, paid model, or other non-disposable
provider is a **live** test: explicit opt-in location or marker, bounded inputs
and cost, and a CI job that cannot run it accidentally.

**Markers** communicate runtime selection; folders communicate navigation and
fixture scope.

- Register `integration`, `contract`, `e2e`, and `live` markers and run with
  `--strict-markers --import-mode=importlib`.
- Derive markers from the directory in the root `conftest.py` collection hook,
  or use a module-level `pytestmark`; never rely on filename suffixes.
- Markers describe execution cost and prerequisites, never business packages.

**CI selection.**

- The ordinary fast suite runs unit and contract tests and excludes live tests
  and any profile whose prerequisites are not provisioned.
- An integration or E2E job provisions its dependency explicitly, selects only
  that profile, and fails fast when the target is absent; it never reports
  success because every test skipped.
- The hermetic job runs `pytest --collect-only` over all profiles so renamed or
  removed behavior breaks every profile in the same change.
- Each profile has a stable direct command so failures reproduce locally.

## Canonical tree

Create only the branches the member uses:

```text
tests/
├── conftest.py                     # Lightweight fixtures, marker hook, safety policy
├── unit/
│   ├── application/
│   ├── domain/
│   ├── adapters/aws/
│   ├── genai/email_classification/
│   └── bootstrap/
├── integration/
│   ├── conftest.py                 # Disposable infrastructure lifecycle only
│   ├── db/
│   └── adapters/
├── contract/
│   ├── architecture/
│   ├── config/
│   └── migrations/
├── e2e/
│   └── conftest.py                 # Whole-system lifecycle and prerequisites
├── fixtures/                       # Sanitized static artifacts shared across profiles
└── <member>_testing/               # Importable support types, when demonstrated
```

A library with a handful of in-process tests keeps them flat at `tests/`. Once a
second profile exists, move every test into an unambiguous profile folder.

## Growth inside a profile

Apply flat-first ([boundaries.md](boundaries.md#flat-first-growth-across-boundaries))
within each profile. Mirror stable source boundaries selectively, prefer a
capability package (`unit/application/email/`) over one package per production
class, and split a module when its tests need different infrastructure, target
unrelated owners, or need different fixture scope. Name modules precisely
(`test_email_admission.py`); the profile is already in the path, so avoid
`_unit`/`_integration` suffixes and multi-owner names such as `test_domain.py`.

## Fixtures and static data

Fixture visibility reveals resource cost:

- Root `tests/conftest.py`: lightweight fixtures, safety hooks, and collection
  policy shared by all profiles.
- `integration/conftest.py`: disposable database, broker, object-store, and
  browser lifecycle; a lower `conftest.py` when only one slice needs it.
- `e2e/conftest.py`: whole-process startup, readiness, and teardown.
- A fixture lives at the narrowest common ancestor of its consumers. Never import
  `conftest.py` as a module.

Static `.json`, `.eml`, workbook, and wire-envelope inputs live in
`fixtures/<capability>/` at the narrowest profile that owns them, sanitized and
minimal. Resolve their paths from `__file__`, never from the working directory.

## Test support packages

Extract a double, builder, or harness once it appears in two or three modules of
a member, or as soon as it subclasses a third-party type or implements a
production port:

- **Instances** (exporter, manual clock, engine, fake runtime) become fixtures in
  the narrowest `conftest.py`.
- **Types** (fake port implementations, builders, recorders) go in a
  member-qualified package, `services/<svc>/tests/<svc>_testing/`. Make it
  importable in exactly one of two ways, and record which one the repository
  uses in the member's pytest configuration:
  - the member's own pytest `pythonpath = ["tests"]` plus the matching mypy
    `mypy_path` entry (default); or
  - an installed dev-only package declared in the member's dev dependencies.

  Import it by its qualified name (`from billing_testing.fakes import
  FakeInvoiceStore`), never by a bare module name, and never add every member's
  `tests/` to a root `pythonpath` (tooling is owned by `python-repository-setup`).
- **Disposable-infrastructure lifecycle** identical across members (test-DB URL
  guard, reset, migrate, dispose) goes in one workspace test-support package or
  pytest plugin, not in copies per member.
- Omit `tests/__init__.py`; the support package has its own `__init__.py`.
  mypy then needs `explicit_package_bases` with the member's `src` and `tests`
  as bases, one run per member
  ([`python-repository-setup` quality-tooling.md, mypy](../../python-repository-setup/references/quality-tooling.md#mypy)).
- Environment variables are read inside fixtures, never at import time.
