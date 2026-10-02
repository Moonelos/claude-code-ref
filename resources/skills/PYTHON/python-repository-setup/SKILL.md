---
name: python-repository-setup
description: >-
  Structure or review a Python repository: a single src-layout project or a uv
  workspace with isolated deployables and reusable packages. Use for dependency
  ownership, lockfiles, toolchain pins, repository-wide quality tooling, Docker,
  Compose orchestration (the environment contract is `python-settings-config`),
  scoped production installs, and workspace admission of shared libraries
  (library design is `python-service-architecture`). Use
  `python-service-architecture` for modules inside a service or library.
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
is not enough. For permitted versus mandatory extraction, see
`../python-service-architecture/references/shared-libraries.md#extraction-triggers`.

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

Good candidates and what each may contain follow the library kinds in
`python-service-architecture` (fallback:
`../python-service-architecture/references/shared-libraries.md#library-kinds-and-importers`):
a stable vendor client, shared wire/schema contracts, database model metadata
consumed by several members, and generic observability plumbing (which may
also own trace/log correlation; outcome decisions stay service-local). Use the
`otel-observability` skill for an observability package's API and lifecycle.

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

Before scaffolding, verify current stable Python and uv releases, confirm them
with the user in one question, and update every pin in a writable template
copy with `scripts/update_toolchain.py --python X.Y.Z --uv A.B.C`. Version
choice, the pin surfaces and their update order, local/CI/Docker alignment,
and the no-mise rule: [references/toolchain.md](references/toolchain.md).

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
restated in prose; the templates' root `pyproject.toml` is the baseline. Read
[references/quality-tooling.md](references/quality-tooling.md) before changing
Ruff, mypy, pytest, or coverage settings. In short:

- Ruff: mandatory absolute imports (`TID252`), complexity ≤ 10 (`C90`),
  package markers (`INP001`); never raise thresholds to pass.
- mypy: `strict` over sources, tests, and every `conftest.py`, with
  `explicit_package_bases`; one run per member in a workspace
  (`scripts/mypy-members.sh`).
- Coverage is reported on the integration CI run, never gated.
- Every directly imported package is declared by the member that imports it.

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
internal architecture. A library's layout, flat-first module growth, public
API, and tests are owned by `python-service-architecture` (fallback:
`../python-service-architecture/references/shared-libraries.md#flat-first`). Use the
domain-specific skill as well when the library has one (for example,
`otel-observability` for a shared telemetry and logging package).

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

The shared dev venv is not a dependency firewall; a scoped install is the real
boundary test ([references/workspace-rationale.md](references/workspace-rationale.md#the-shared-dev-environment-is-not-a-dependency-firewall)).

## Lean Production Docker Images

Every shipped build passes `--no-dev` (the root `dev` group is installed even
with `--package`), builds from the repository root as context, and uses the
canonical multi-stage Dockerfile. Single-service adaptation, build context,
sync flags, `.dockerignore`, and service variants: read
[references/docker-builds.md](references/docker-builds.md) before creating or
editing an image.

## Templates

Copy one of the two canonical runnable scaffolds instead of recreating these
files from memory:

- **Single deployable:** `assets/single-service-template/`: a FastAPI service
  in `src/sample_service/` (the `bootstrap/` and `api/` boundaries of
  `python-service-architecture`, started by `uvicorn --factory`), tests with
  two `conftest.py` files, the root `Dockerfile`, `compose.yaml`,
  `.env.example`, pre-commit hooks, and the CI workflow.
- **Workspace:** `assets/workspace-template/`: a FastAPI service, an internal
  library, the workspace-aware Dockerfile, the per-member mypy script,
  `compose.yaml`, the root and per-service `.env.example`, and the same hooks
  and workflow.

Both carry exact toolchain pins and the same Ruff, pytest, coverage, mypy,
import-linter, pre-commit, and CI decisions
([CI parity](references/pre-commit.md#ci-parity)); `tests/test_templates.py`
fails when they drift, so change a shared rule in both. Rename `sample_service`
(or `sample_api`) everywhere, including `known-first-party`, coverage `source`,
and the import-linter contracts.

## Docker Compose And Root `.env`

Read [references/docker-compose.md](references/docker-compose.md) whenever
creating or reviewing `compose.yaml`, the root `.env.example`, service
environment mapping, or local container startup. Each deployable's own
`.env.example` contract is owned by `python-settings-config` (fallback:
`../python-settings-config/references/env-example.md`).

## Setup And Verification

After adapting a template, run the commands in
[references/verification.md](references/verification.md) from the repository
root. A workspace root is virtual, so it syncs with
`uv sync --frozen --all-packages` (as the template CI does); a plain
`uv sync --frozen` installs no members. A single service uses
`uv sync --frozen`.

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

Two services that always deploy together as one release unit do not need the
separation. Whether candidate library code stays inside its owning service
(one consumer, similar code with different meaning) is decided by
`python-service-architecture`
(`../python-service-architecture/references/shared-libraries.md#extraction-triggers`);
the workspace is not a mandate to maximize package count.

## Related Skills

- `terraform-aws`, `deploy-scripts`, `split-repo-app-releases`: how each
  service's image is built and shipped in CI, and whether Terraform and
  application source share a repository. A Lambda's `handler.py`/`src/`
  boundary and ZIP vs. container packaging:
  `../terraform-aws/references/python-lambda.md`; a Lambda sharing code through
  a uv workspace follows this skill for the layout and that reference for
  packaging.
- `python-service-architecture`: internal modularization of services and
  shared libraries.
- `otel-observability`: API, lifecycle, and migration of a shared
  observability package; `python-logging` for its logging policy. This skill
  owns only whether it earns a workspace member and how consumers install it.
