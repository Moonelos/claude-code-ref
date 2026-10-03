# Pre-commit and pre-push in a Python repository

Use this reference in single-service and workspace repositories when creating,
reviewing, or changing the repository-root
`.pre-commit-config.yaml`; aligning hooks with uv/Ruff/CI versions; adding or
moving workspace members; or debugging local/CI hook differences.

## Ownership and discovery

`.pre-commit-config.yaml` is repo-wide development tooling. Keep one at the
repository root beside `pyproject.toml` and `uv.lock`. Do not put independent
configs inside services or libraries unless they are separate repositories.

Before editing it, inspect:

- the root `pyproject.toml`, `uv.lock`, and `.python-version`;
- existing hook stages, exclusions, file filters, and local hook commands;
- actual Python roots from the repository tree and, when present,
  `[tool.uv.workspace]`; `src`/`tests` and `services`/`libs` are mode-specific
  examples, not hard names;
- CI quality jobs and their Python/uv versions;
- Docker pins when a tool version is shared with image builds;
- domain-specific checks already owned by another skill, such as ShellCheck or
  Terraform validation from `deploy-scripts`/`terraform-aws`.

Preserve useful repository hooks and policies. Adding Python workspace support
does not authorize replacing security, shell, Terraform, generated-file, or
organisation-specific checks.

## Stage policy

Use hook stages to keep ordinary commits responsive without weakening the
quality gate:

| Stage | Suitable work |
| --- | --- |
| `pre-commit` | trailing whitespace, syntax/config validation, Ruff lint/format, lockfile freshness, secret scanning, other fast filename-based checks |
| `pre-push` | workspace-wide mypy, non-live pytest, build/contract checks, or tools that ignore filenames and scan large trees |
| CI | the complete required gate, including the fast pre-commit stage plus explicit type, test, integration, build, and deployment checks selected by the repository |

Do not put the full test suite or a workspace-wide type check on every commit by
default. Do not make a required check local-only: developers can bypass hooks,
and CI must enforce the equivalent outcome.

When `default_install_hook_types` includes both stages, an ordinary
`pre-commit install` installs both hook scripts. Otherwise document or run the
explicit installation commands appropriate to the repository.

## Hook execution environments

Use upstream hooks for tools designed to receive changed filenames. They run in
their own pre-commit-managed environment:

- `pre-commit/pre-commit-hooks` for format and config sanity checks;
- `astral-sh/ruff-pre-commit` for Ruff lint and formatting;
- `astral-sh/uv-pre-commit` for `uv-lock`.

Use `repo: local`, `language: system`, and `uv run --locked ...` for hooks that
need the workspace environment, internal packages, or root dev dependencies.
Set `pass_filenames: false` only when the command intentionally selects its own
complete scope. Use `always_run: true` for a required workspace-wide gate whose
scope cannot be inferred safely from changed paths.

`--locked` is load-bearing: a hook must fail when declared dependencies and
`uv.lock` disagree, not rewrite the lock opportunistically. The dedicated
`uv-lock` hook owns lockfile updates/checks. Do not run `uv sync` inside a hook;
it mutates the environment and makes commit latency/network behavior
unpredictable.

## Version alignment

Keep one selected version per tool across every place that executes it:

| Tool | Align |
| --- | --- |
| uv | root `[tool.uv].required-version`, `uv-pre-commit` revision, CI setup, and Docker `UV_VERSION` |
| Ruff | root dev dependency/lock, `ruff-pre-commit` revision, and any CI invocation |
| Python | `.python-version`, member `requires-python`, CI, and Docker |
| pre-commit | root dev dependency/lock and CI invocation environment |

For a ranged root dependency, compare the hook revision with the version
actually resolved in `uv.lock`, not merely the lower bound. Update all owners in
one deliberate toolchain upgrade. Do not run `pre-commit autoupdate` and accept
unrelated revisions without checking compatibility and corresponding pins.

## Canonical shape

Copy the template's file and adapt roots, versions, exclusions, and
domain-specific hooks to the repository:
[workspace](../assets/workspace-template/.pre-commit-config.yaml),
[single service](../assets/single-service-template/.pre-commit-config.yaml).
Both install both stages (`default_install_hook_types: [pre-commit, pre-push]`)
and run, in order: `pre-commit-hooks` sanity checks, `ruff-check --fix` and
`ruff-format`, `uv-lock`, then local hooks for import-linter (pre-commit
stage), mypy and non-live pytest (`-m "not live and not integration and not e2e"`,
pre-push stage). The two files differ only in the mypy hook: the workspace
entry is `scripts/mypy-members.sh` (one mypy run per member; see
[quality-tooling.md](quality-tooling.md#mypy)), the single service runs
`uv run --locked mypy src tests`.

The template roots are placeholders. If the repository uses `apps/`,
`components/`, `packages/`, Lambda roots, top-level contract tests, or other
owned Python trees, derive the mypy/pytest scope from the real configuration and
CI. Do not rename the repository or introduce parallel roots to fit the
template.

`ruff-check --fix` intentionally modifies files locally. In CI the same hook
runs against a clean checkout and fails when it would make a change. If the
project prohibits modifying hooks, remove `--fix` deliberately in both local
and documented behavior rather than relying on context-dependent arguments.

## Architecture contracts

Services follow the hexagonal shape in `python-service-architecture` (fallback:
`../../python-service-architecture/SKILL.md`). Agents write most of the code, so
its dependency rules are enforced by a tool on every commit, not only described.
Add `import-linter` to the root `dev` dependency group and declare one set of
contracts per service in the root `pyproject.toml`. The four service contracts
are in the template's root `pyproject.toml` ([workspace](../assets/workspace-template/pyproject.toml), service
`sample_api`; [single service](../assets/single-service-template/pyproject.toml),
`sample_service`), under `[tool.importlinter]` with
`include_external_packages = true`:

1. **application uses only admitted inner dependencies:** sources
   `<svc>.application.**`; forbids `adapters`, `api`, `bootstrap`, `config`,
   `db`, `genai`, `workers`, and the external list.
   `allow_indirect_imports = true`, because application → observability →
   opentelemetry is the allowed telemetry path.
2. **domain and ports are pure:** sources `<svc>.domain.**` and
   `<svc>.ports.**`; forbids every other boundary, including `application`
   and `observability`, and the external list.
3. **only entry points import bootstrap:** sources `adapters`, `api`, `db`,
   `genai`, and `workers` (each `.**`); forbids `<svc>.bootstrap`.
4. **entry points use actions and contracts, not concrete integrations:**
   sources `<svc>.api.**` and `<svc>.workers.**`; forbids `adapters`, `config`,
   `db`, and `genai`. `allow_indirect_imports = true`: only direct imports are
   forbidden, because runtime wiring is in bootstrap and telemetry helpers may
   have their own outer integrations.

The external list names the SDKs and frameworks the service depends on; extend
it when a dependency is added. The template lists `fastapi` and
`opentelemetry`; a service with more integrations adds, for example, `boto3`,
`httpx`, `langchain_core`, `sqlalchemy`, and `sqlmodel`. `include_external_packages` is required for
those entries. import-linter can only forbid what is listed, so this list is a
floor: `python-service-architecture-audit` checks the inverse, flagging any
third-party import in those packages outside a small allow-list.

The internal lists are fixed: every contract names every canonical boundary
(`adapters`, `api`, `application`, `bootstrap`, `config`, `db`, `genai`,
`observability`, `workers`) whether or not the service has it yet, so a
boundary added later is covered the day it appears. Do not tailor them to the
current tree. Commit the contracts with the service, before its boundaries exist. A missing
*forbidden* module is ignored, but a missing *source* module is an error, so
sources use the `package.**` form, which matches nothing until the package has
modules. `.**` matches descendants only, not the package's own `__init__.py`;
those files stay empty package markers (`python-code-conventions`, "Imports and
package markers"), so `.**` alone is the one rule for service-layer sources.
A library's root package always exists and its `__init__.py` holds the public
API, so a library's independence contract names the root itself, which
import-linter treats as a package covering every descendant.

Repeat the four contracts for each service. A migration runner that has no
application code (`python-sqlmodel-alembic`, "Monorepo (uv workspace)") is not a
service and gets none of them; add one contract instead that forbids every
service package from importing `alembic` and the runner package.

Every workspace library also gets an independence contract, and each service
restricts which of its layers may import each library. The library kinds and
their allowed importers are defined in `python-service-architecture` (fallback:
`../../python-service-architecture/references/shared-libraries.md`, "Library
kinds and importers"). List the library in `root_packages`:

```toml
[[tool.importlinter.contracts]]
name = "docstore_client: independent of every service"
type = "forbidden"
source_modules = ["docstore_client"]
forbidden_modules = ["orchestrator", "worker", "pydantic_settings"]

# A client library: only the port implementations (adapters, genai) and
# bootstrap import it.
[[tool.importlinter.contracts]]
name = "orchestrator: docstore_client only in adapters, genai, and bootstrap"
type = "forbidden"
source_modules = [
    "orchestrator.api.**",
    "orchestrator.application.**",
    "orchestrator.config.**",
    "orchestrator.db.**",
    "orchestrator.domain.**",
    "orchestrator.observability.**",
    "orchestrator.ports.**",
    "orchestrator.workers.**",
]
forbidden_modules = ["docstore_client"]
```

For a configuration library, omit `pydantic_settings` from its independence
contract and forbid its imports from every service layer except `config` and
`bootstrap`. For a genai library, permit `genai` and `bootstrap` (bootstrap
constructs only its input types and provider client; review, not the contract,
checks that). For
the documented database-runtime exception, permit `db` and `bootstrap`; see the
owning shared-library reference for declaration and review.

A persistence (models) library gets the same importer contract with every
layer except `db` as a source. A contract library needs no importer contract.
Add each new service package to every library's independence contract in the
same change that creates the service.

Run it in the `pre-commit` stage; it analyzes the whole import graph in
seconds. The templates' `import-linter` hook (`uv run --locked lint-imports`,
`pass_filenames: false`, `always_run: true`) does this.

CI runs the same `uv run --locked lint-imports`. A broken contract is fixed in
the code, never by editing the contract to match.

## CI parity

Both templates ship `.github/workflows/ci.yml` with two jobs; create the
equivalent for another CI system when the service is created, not later:

- **checks:** both hook stages on the complete checkout, so CI enforces exactly
  what developers run (Ruff, `uv-lock`, import-linter contracts, per-member
  mypy, the fast test suite);
- **integration:** a disposable PostgreSQL service and every non-live profile,
  with coverage reported. Tests reach it through `INTEGRATION_APP_DATABASE_URL`
  pointing at a `test_`-prefixed database, never the service `DATABASE_URL`
  (contract owner: `../../python-sqlmodel-alembic/references/schema-verification.md#disposable-test-databases`).
  The job sets `REQUIRE_INTEGRATION=1`, so a missing
  database URL fails instead of skipping and a job that lost its database
  cannot pass (`../../pytest/references/examples-core.md`, "Profile
  prerequisites").

At minimum, CI runs the fast stage against the complete checkout:

```bash
uv run --locked pre-commit run --all-files --hook-stage pre-commit
```

CI may run pre-push hooks directly:

```bash
uv run --locked pre-commit run --all-files --hook-stage pre-push
```

or run equivalent explicit mypy/pytest commands in dedicated jobs. Avoid doing
both unless the duplication is intentional. Compare command arguments, markers,
paths, Python/uv versions, and environment prerequisites—not just tool names.

Integration, E2E, live-provider, Docker, Terraform, and deployment checks
normally stay in dedicated CI jobs with their required infrastructure. Do not
force them into ordinary pre-push merely to make one file list every check.

## Adding or moving members

When a service, library, Lambda, or repository-owned test root is added, moved,
or renamed:

1. update workspace membership and package metadata first;
2. search pre-commit local-hook entries, `files`/`exclude` expressions, mypy
   paths, pytest collection, coverage sources, and CI commands for explicit old
   roots;
3. update only affected scopes—do not broaden unrelated domain hooks;
4. run the fast stage against all files and the relevant pre-push/CI-equivalent
   checks;
5. run a package-scoped install for each affected member: the shared developer
   environment hides dependency leakage
   ([workspace-rationale.md](workspace-rationale.md#the-shared-dev-environment-is-not-a-dependency-firewall)).

Do not exclude a new member from lint/type/test hooks simply to make the hook
pass. Fix its configuration, give it an explicit justified profile, or report
the incompatible boundary.

## Verification

Run the hook-stage commands and the confirmation checklist in
[verification.md](verification.md#environment-and-quality-gate), including
`pre-commit validate-config`.
