---
name: python-repository-setup
description: >-
  Structure or review a Python repository: a single src-layout project or a uv
  workspace with isolated deployables and reusable packages. Use for dependency
  ownership, lockfiles, toolchain pins, repository-wide quality tooling, Docker,
  Compose, and scoped production installs. Use `python-service-architecture` for
  modules inside a service or library.
---

# Python Repository Setup: Single Service or uv Workspace

Choose the repository mode before generating files:

- **Single deployable:** keep `pyproject.toml`, `uv.lock`, `.python-version`,
  `Dockerfile`, `compose.yaml`, `src/<package>/`, and `tests/` at the repository
  root. Do not create `services/`, `libs/`, or a uv workspace pre-emptively.
- **Multiple independently deployable artifacts:** use a virtual uv workspace.
  Every deployable lives under `services/` with its own `pyproject.toml`; truly
  reusable internal packages live under one consistent `libs/` or `packages/`
  root and also own their `pyproject.toml`.

The tooling and operational standards in this skill apply to both modes:
version pins, one repository lockfile, Ruff, pytest, coverage, mypy,
pre-commit/pre-push, Docker, Compose, and CI alignment. Workspace-only mechanics
such as member globs, `{ workspace = true }`, `--package`, and a virtual root
apply only to the multi-deployable mode.

For workspace mode, apply this rule:

> **Independently deployable = its own `pyproject.toml`. Genuinely reusable
> internal code = its own `pyproject.toml`. The root `pyproject.toml` declares
> the workspace and repo-wide development tooling, but no runtime dependencies
> any service ships.**

Service dependency ownership and YAML configuration ownership are independent.
Although every deployable owns its `pyproject.toml`, a multi-service repository
uses one repository-root `config/` for committed YAML application baselines by
default. Do not create `services/<name>/config/*.yaml` merely because each
service has its own project file. Use service-local YAML directories only when
the user explicitly requests per-service configuration ownership. Apply the
layout and merge precedence defined by `python-settings-config`; package-local Python
settings modules remain governed by `python-service-architecture`.

Workspace mode applies once a repository holds more than one independently
built artifact (Dockerfile, Lambda, or deployed process).

## Repository Layouts

Single deployable:

```text
repo/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .pre-commit-config.yaml
├── .env.example
├── Dockerfile
├── compose.yaml
├── src/
│   └── my_service/
└── tests/
```

Do not place the package directly at `src/`; use `src/<import_package>/`.
The root `pyproject.toml` owns both runtime dependencies and repository-wide
development tooling.

## Naming The Top-Level Directory: `services/` vs `libs/`/`packages/`

The names are a semantic choice, not a uv requirement:

- **`services/`** — every independently deployable unit: an API, a worker, a
  queue consumer, a scheduled batch job, a CLI, a frontend build. Use this name
  even in a worker-only repository, and don't add an `apps/` directory
  alongside it.
- **`libs/`** or **`packages/`** — cohesive reusable internal code with no
  deployable of its own: consumed by other members via `{ workspace = true }`,
  never has its own `Dockerfile`. A directory does not become a library merely
  by being placed here; apply the admission test below. Pick one top-level name
  and use it consistently.

The rest of this skill illustrates the setup with `services/api` and
`services/worker` because that's the common case for a Python workspace.

## Before Creating A Shared Library

A workspace member adds a public contract, dependency edge, test surface, and
migration cost. Create one only when the code has one cohesive meaning outside
any single deployable and there is concrete reuse: normally at least two current
consumers, or an independently valuable protocol/client/schema boundary with a
concrete compatibility or dependency-isolation reason. Hypothetical reuse alone
is not enough.

Check all of these before adding `libs/<name>`:

- the candidate removes duplicated behavior or publishes one stable contract,
  not merely similar syntax;
- its inputs and outputs can be expressed without importing a service's private
  settings, application, domain, bootstrap, or tests;
- its dependencies are appropriate for every consumer and do not pull one
  service's framework or vendor stack into unrelated images;
- it has one reason to change and will not become a `common`, `shared`, `utils`,
  or organisation-wide dumping ground;
- consumers can migrate independently through an additive API when an atomic
  move is unsafe;
- owning it as a package improves consistency, dependency direction, testing,
  or release safety enough to justify the boundary.

Good candidates include a stable vendor client, shared wire/schema contracts,
database model metadata consumed by several members, and generic observability
plumbing. An observability library may coherently own provider lifecycle, span
helpers, propagation, trace/log correlation, redaction, and shared structured-
logging processors when those policies are common. Service span names, business
metrics, event vocabulary, and outcome decisions remain service-local. Use the
`otel-observability` skill for that package's API and lifecycle.

## Workspace Layout

Why one shared root dependency list fails, and what the shared dev environment
does not guarantee: [references/workspace-rationale.md](references/workspace-rationale.md).

```text
repo/
├── pyproject.toml              # virtual root: workspace + shared dev tooling
├── uv.lock                     # single lockfile for the entire workspace
├── .python-version             # exact local/CI/Docker Python patch
├── .dockerignore               # must not exclude .python-version
│
├── services/
│   ├── api/
│   │   ├── pyproject.toml      # api's own dependencies
│   │   ├── Dockerfile
│   │   └── src/
│   │       └── api/
│   │           └── main.py
│   │
│   └── worker/
│       ├── pyproject.toml      # worker's own dependencies
│       ├── Dockerfile
│       └── src/
│           └── worker/
│               └── main.py
│
└── libs/
    └── company_observability/
        ├── pyproject.toml
        └── src/
            └── company_observability/
                ├── __init__.py
                ├── config.py
                ├── providers.py
                ├── spans.py
                ├── propagation.py
                └── logging.py
```

Use plural glob members (`services/*`, `libs/*`) rather than an explicit list.
An explicit list silently excludes a new service that forgets to update it; a
glob has no such failure mode.

## Choose And Align Toolchain Versions First

Before scaffolding, verify the current stable patch release for the chosen
Python minor and the current stable uv release from official sources. Propose
the defaults, then ask one concise question: “I will use Python X.Y.Z and uv
A.B.C; do you want different versions?” Skip the question when the user has
already supplied both versions. When nobody can be asked (a delegated agent, a
non-interactive run), use the installed uv and Python if they are stable
releases of the intended minor, otherwise the template's pins, and state the
chosen pins as an assumption in the handoff. After copying the bundled asset
to a writable location and before using it, update its single toolchain
manifest and every derived pin with
`scripts/update_toolchain.py --python X.Y.Z --uv A.B.C`; do not hand-edit a
subset of the copies. Run that script on a writable copy of the template,
never on the installed skill source. When constructing a service without
copying the template, set all new toolchain pins coherently and run the
equivalent pin checks in that service; the template update script does not
apply to files it does not own.

The bundled template snapshot currently uses:

- Python `3.13.15`, with `.python-version` containing exactly `3.13.15`.
- uv `0.12.7`.
- Every member: `requires-python = ">=3.13,<3.14"`.

Apply them in this order:

1. Put `requires-python = ">=3.13,<3.14"` in every service and library
   `pyproject.toml`.
2. Run `uv python pin 3.13.15` at the workspace root to create
   `.python-version`.
3. Read that exact value into each Dockerfile's `ARG PYTHON_VERSION` default
   and keep the in-build equality check.
4. Put `required-version = "==0.12.7"` in the root `[tool.uv]` table and use
   the same exact uv version in Docker and CI.

Treat these as a coherent set. If the user changes the Python minor, update
all member `requires-python` ranges, Ruff's `target-version`,
`.python-version`, the Docker `PYTHON_VERSION`, and CI. If only the patch
changes within 3.13, update `.python-version`, Docker, and CI. If uv changes,
update root `required-version`, Docker, and CI.

Do not add mise. Let uv read `.python-version` locally; `uv python install`
can install the pinned interpreter when needed. A Dockerfile cannot derive a
pre-`FROM` `ARG` from a file in the build context, so repeat the exact Python
pin in `ARG PYTHON_VERSION` and fail the build if it differs from
`.python-version`.

In CI, install the exact root `required-version`, run `uv python install`, and
then use the root lockfile. `required-version` enforces the uv pin but does not
install the matching uv binary by itself.

## `pyproject.toml` Ownership

- **Single deployable:** the root is an ordinary installable project with
  runtime dependencies in `[project.dependencies]`, repo-wide tools in the root
  `dev` group, and one root `uv.lock`. No `[tool.uv.workspace]`, no `--package`.
- **Workspace:** the root is *virtual* — no `[project]`, no
  `[project.dependencies]`, no `[build-system]`. It only declares members,
  anchors the single `uv.lock`, pins uv (`required-version`), and holds the
  shared `dev` group plus Ruff/pytest/coverage/mypy tables. Framework-specific
  test plugins or stubs used by one member go in that member's own group.
- **Every installable member** (service or library) owns its `pyproject.toml`
  with `requires-python`, only the dependencies it imports, a
  `src/<import_package>/` layout matching the project name (hyphens →
  underscores), and `{ workspace = true }` sources for internal libraries it
  consumes.

Read [references/pyproject-files.md](references/pyproject-files.md) for the
concrete root, service, and library files before writing or reviewing one.

## Lint, Type, And Test Baseline

Any rule a linter or type checker can enforce is enforced in configuration, not
restated in prose. The template's `[tool.ruff.lint]` table is the baseline; each
rule family carries its one-line rationale there.

- `TID252` with `ban-relative-imports = "all"` is mandatory: absolute imports
  only.
- `C90` with `max-complexity = 10` enforces complexity. Ruff cannot measure
  function length or nesting; those stay review signals, with the numbers in
  `python-code-conventions` (fallback: `../python-code-conventions/SKILL.md`,
  "Size signals").
- `INP001` requires `__init__.py` in every package directory (rule owner:
  `python-code-conventions`, "Imports and package markers"). Test directories
  (`**/tests/**`) and Alembic script directories (`**/alembic/**`) are exempt:
  tests run under `--import-mode=importlib` without package markers, and
  Alembic loads its scripts by path.
- List every import package and each member's test-support package
  (`<member>_testing`) in `[tool.ruff.lint.isort] known-first-party`; Ruff
  cannot discover a package that lives under `tests/`.
- Do not enable `PLR0913` (keyword-only DI constructors legitimately exceed it)
  or `EM`/`TRY003` (high volume, little value). `ANN401`, `FBT001`, and
  `PLR2004` are optional; if enabled, exempt true adapters from `ANN401` and
  tests from `PLR2004` through `per-file-ignores`.
- When introducing the baseline into existing code, fix each finding or add a
  `# noqa: <CODE> <reason>`. Never raise thresholds or broaden ignores to pass.

mypy runs `strict` with `warn_unreachable` and the `ignore-without-code`,
`redundant-expr`, and `possibly-undefined` error codes. Add
`plugins = ["pydantic.mypy"]` whenever any member uses pydantic. The mypy paths
include tests, test-support packages, and every `conftest.py`; never exclude
them. Because tests have no `__init__.py` and several `conftest.py` files, set
`explicit_package_bases = true` and give mypy each member's `src` and `tests`
as bases:

- **Single deployable:** `mypy_path = ["src", "tests"]` and `mypy src tests`.
- **Workspace:** run mypy once per member with
  `MYPYPATH=<member>/src:<member>/tests` (`scripts/mypy-members.sh` in the
  template). One run over every member fails with "Duplicate module named
  conftest", because each member's `tests/conftest.py` is a top-level
  `conftest`. Libraries ship `py.typed` so consumers type-check against them. For third-party types, add `boto3-stubs`/`types-*` to the dev group; for a
package with no stubs, list it in one `[[tool.mypy.overrides]]` block with
`ignore_missing_imports = true`, never per-import `# type: ignore[import-untyped]`.

Every package a member imports directly is declared in that member's
`dependencies` (or dev group, for test-only imports); an install that arrives
transitively is not a declaration.

Coverage is reported, not gated: the default `pytest` run collects none, and
the CI job that runs every non-live profile against real infrastructure reports
it with `--cov`, because only that run exercises `db/` and migrations. Coverage
`source` lists every workspace import package and omits Alembic's `env.py` and
`versions/`. Do not add `fail_under`; coverage is a map for review
(`pytest`, fallback: `../pytest/SKILL.md`).

The root `testpaths` lists member roots for discovery only. Do not add a root
`pythonpath` listing every member; make shared test support importable per
member as described in `../python-service-architecture/references/testing.md`
("Test support packages"). Async tests are native `async def` under the one
async plugin the repository already uses (anyio or pytest-asyncio); test design
belongs to the `pytest` skill.

## Pre-commit And Pre-push

Read [references/pre-commit.md](references/pre-commit.md) whenever creating or
reviewing `.pre-commit-config.yaml`, changing a repo-wide tool version, adding or
moving a workspace member/root, changing quality commands in CI, or diagnosing
hooks that pass locally but fail in a scoped or clean environment.

The configuration is root-owned development tooling. Keep fast, filename-based
checks in the `pre-commit` stage and reserve workspace-wide type/test checks for
`pre-push` or CI. Local hooks that need the uv environment run through
`uv run --locked`; hook versions, root tool pins, CI, and Docker must not drift.
Discover the repository's actual service and internal-library roots rather than
assuming the example `services/` and `libs/` names. Every repository with a
hexagonal service also runs import-linter architecture contracts in pre-commit
and CI ([pre-commit.md](references/pre-commit.md#architecture-contracts)).

## Internal Library Layout

This skill owns the workspace boundary and installation mechanics, not a rigid
internal architecture. Every library still uses `src/<import_package>/`, keeps
tests beside the member, exposes a small intentional public API, and starts with
the fewest cohesive modules. Do not copy a deployable's `main.py`, `bootstrap/`,
`application/`, `adapters/`, and `config/` shell into a non-deployable library.

Keep a small package flat. Introduce a subpackage only when one narrower
capability has several cohesive modules, changes independently, needs distinct
test setup, or causes real naming pressure. Avoid file-per-class layouts,
one-file subpackages, speculative registries/factories, and generic `common`,
`shared`, `utils`, or `core` packages.

Use the `python-service-architecture` skill's shared-library guidance for detailed
module ownership, dependency direction, public exports, tests, and
consumer-by-consumer modularization. Use the domain-specific skill as well when
the library has one—for example, `otel-observability` determines the internals of a
shared telemetry and logging package.

## One Lockfile, Scoped Installs

This is the mechanism that actually delivers the isolation, and it is easy to
get wrong by assuming the opposite:

- **There is exactly one `uv.lock`, at the workspace root**, resolving every
  member together. Do not hand-write a `uv.lock` inside `services/api/` — uv
  does not create or read one there, and one left behind by mistake is just
  dead weight.
- `uv lock` always operates on the whole workspace.
- Use `uv sync --all-packages` explicitly when the intended local environment
  contains every workspace member. Do not rely on virtual-root behavior that may
  vary by uv version or invocation directory. That shared environment is the
  intended local dev setup — you can edit `api`, `worker`, and
  `company_observability` together with one interpreter, one `pytest` run, one
  IDE environment.
- `uv sync --package api` (or `uv run --package api …`, `uv export --package
  api`) scopes to `api` **and its transitive workspace dependencies only**.

The shared dev venv is not a dependency firewall: a scoped
`uv sync --package <service>` (or the Docker build itself) is the real test of
a member's dependency boundary.

### Root Dev Dependencies and Docker

A root `[dependency-groups] dev = [...]` group is installed **by default even
with `--package`**. Always pass `--no-dev` (or `--only-group
<name>` for a narrower selection) alongside `--package` when building anything
that ships, or the "lean image" goal quietly fails:

```bash
uv sync --frozen --no-dev --package api
```

## Lean Production Docker Images

For a single service, build the root `Dockerfile` from the repository root. Use
the same pins, multi-stage split, locked non-editable install, non-root runtime,
and secret rules as workspace images, without workspace metadata, `--package`,
or `--no-install-workspace`.

Build each service's image from the **workspace root** as the build context —
not from inside `services/api/` — because resolving `api`'s dependencies
still requires the root `pyproject.toml`, the shared `uv.lock`, and the source
of every workspace member `api` imports (at minimum `libs/company_observability/`).
Scoping the build context to just `services/api/` is a common mistake that
breaks the build the moment a service depends on a shared library. Full
production Dockerfile, `.dockerignore`, version-alignment checks, and build
commands for both modes: read
[references/docker-builds.md](references/docker-builds.md) before creating or
editing an image.

Copy one of the two canonical runnable scaffolds instead of recreating these
files from memory:

- **Single deployable:** `assets/single-service-template/`: a FastAPI service
  in `src/sample_service/` (the `bootstrap/` and `api/` boundaries of
  `python-service-architecture`, started by `uvicorn --factory`), tests with
  two `conftest.py` files, the root `Dockerfile`, `compose.yaml`,
  `.env.example`, pre-commit hooks, and the CI workflow.
- **Workspace:** `assets/workspace-template/`: a FastAPI service, an internal
  library, the workspace-aware Dockerfile, the per-member mypy script, and the
  same hooks and workflow.

Both carry exact toolchain pins and the same Ruff, pytest, coverage, mypy,
import-linter, pre-commit, and CI decisions
([CI parity](references/pre-commit.md#ci-parity)); `tests/test_templates.py`
fails when they drift, so change a shared rule in both. Rename `sample_service`
(or `sample_api`) everywhere, including `known-first-party`, coverage `source`,
and the import-linter contracts.

## Docker Compose And Root `.env`

Read [references/docker-compose.md](references/docker-compose.md) whenever
creating or reviewing `compose.yaml`, root `.env.example`, service environment
mapping, or local container startup. Compose uses one ignored root `.env` as
the local stack input. Declare each service's `environment:` mapping explicitly;
do not attach the whole root file to every container with `env_file: .env`.
Keep the root `.env.example` focused on values the user must configure or
consciously choose for the local Compose stack. For each service, put required
runtime environment variables in active assignments and optional overrides of
committed config in commented-out assignments in its `.env.example`; see the
reference for the single-service case.

## Setup And Verification

After adapting the template, run the applicable commands from the repository
root. For both modes:

```bash
uv python install
uv lock --check
uv sync --frozen
uv run --locked pre-commit install
uv run --locked pre-commit run --all-files --hook-stage pre-commit
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests            # single deployable; workspace: scripts/mypy-members.sh
uv run pytest
uv run --locked pre-commit run --all-files --hook-stage pre-push
docker compose config --quiet
docker compose up --build
```

For workspace mode, additionally run:

```bash
uv sync --frozen --all-packages
uv sync --frozen --no-dev --package <service>
docker build --pull -f services/<service>/Dockerfile .
```

For a single service, instead use `uv sync --frozen --no-dev` and
`docker build --pull -f Dockerfile .`.

Also verify the version contract explicitly:

```bash
python scripts/update_toolchain.py --check
test "$(uv run python -c 'import platform; print(platform.python_version())')" = "$(tr -d '\r\n' < .python-version)"
uv --version
```

Run the toolchain check from this skill package before copying the asset; after
copying, use the remaining checks from the generated repository root.

The final expected ownership is:

| Environment | Python | uv |
| --- | --- | --- |
| Local project | exact `.python-version` | exact root `required-version` |
| CI | exact `.python-version` | exact root `required-version` |
| Docker builder | exact `PYTHON_VERSION` | exact `UV_VERSION` |
| Docker runtime | exact `PYTHON_VERSION` | absent |

## Adding a Service or Library

1. For a proposed library, apply [Before Creating A Shared Library](#before-creating-a-shared-library)
   and keep the code service-local if it does not earn the boundary.
2. Create `services/<name>/` (or `libs/<name>/` — see
   [Naming The Top-Level Directory](#naming-the-top-level-directory-services-vs-libspackages)
   above) with `src/<package>/` and a `pyproject.toml` declaring only that
   member's own dependencies.
3. If it consumes a shared library, add the library by name to `dependencies`
   and add `<library> = { workspace = true }` under `[tool.uv.sources]`.
4. Confirm it's picked up: `services/*` and `libs/*` globs cover it
   automatically; an explicit `members` list needs a new line.
5. Inspect `.pre-commit-config.yaml` and CI for explicit paths or filters; update
   them for the new member/root without broadening unrelated hooks.
6. Run `uv lock` at the root to fold it into the shared lockfile, then `uv sync
   --package <name>` for the new member and each consumer to verify the expected
   dependency closures without sibling-service leakage.
7. Run the library's own tests independently, then the focused contract and
   startup/lifecycle tests of each migrated consumer.
8. Add a Dockerfile only for a deployable. A `libs/*` member is included through
   each consumer's workspace-root build context and never has its own image.

## When Not To Split

Two services that always deploy together as one release unit, or candidate
library code with one consumer and no independent stable contract, do not need
the separation. Similar code that carries different business semantics should
also remain duplicated until a real common contract emerges. Keeping it inside
its owning service is a legitimate simplification—the workspace is not a
mandate to maximize package count.

## Related Skills

This skill covers the Python package/dependency structure inside the
repository. It does not cover how each service's image gets built and shipped
in CI, or whether Terraform and application source share a repository — those
decisions belong to the `terraform-aws`, `deploy-scripts`, and
`split-repo-app-releases` skills. For a Lambda function's `handler.py`/`src/`
boundary and packaging (ZIP vs. container), see `terraform-aws`'s
`../terraform-aws/references/python-lambda.md`; a Lambda that shares code with other functions
through a uv workspace follows this skill for the workspace layout and that
reference for the AWS-specific packaging step.

Use `python-service-architecture` for the internal modularization of services and
shared libraries. Use `otel-observability` for the API, lifecycle, and migration of a shared
observability package (`python-logging` for its logging policy); this skill owns only whether
it earns a workspace member and how consumers install it.
