# Lint, Type, And Test Baseline

Ruff, mypy, pytest, and coverage configuration for both repository modes. The
tables themselves are in the templates' root `pyproject.toml`
([workspace](../assets/workspace-template/pyproject.toml),
[single service](../assets/single-service-template/pyproject.toml)); this file
explains the decisions behind them. Hooks and CI that run these tools:
[pre-commit.md](pre-commit.md).

## Ruff

Any rule a linter or type checker can enforce is enforced in configuration, not
restated in prose. The template's `[tool.ruff.lint]` table is the baseline; each
rule family carries its one-line rationale there.

- `TID252` with `ban-relative-imports = "all"` is mandatory: absolute imports
  only.
- `C90` with `max-complexity = 10` enforces complexity. Ruff cannot measure
  function length or nesting; those stay review signals, with the numbers in
  `python-code-conventions` (fallback: `../../python-code-conventions/SKILL.md`,
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

## mypy

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
  `conftest`.

Libraries ship `py.typed` so consumers type-check against them. For
third-party types, add `boto3-stubs`/`types-*` to the dev group; for a package
with no stubs, list it in one `[[tool.mypy.overrides]]` block with
`ignore_missing_imports = true`, never per-import
`# type: ignore[import-untyped]`.

Every package a member imports directly is declared in that member's
`dependencies` (or dev group, for test-only imports); an install that arrives
transitively is not a declaration.

## Coverage

Coverage is reported, not gated: the default `pytest` run collects none, and
the CI job that runs every non-live profile against real infrastructure reports
it with `--cov`, because only that run exercises `db/` and migrations. Coverage
`source` lists every workspace import package and omits Alembic's `env.py` and
`versions/`. Do not add `fail_under`; coverage is a map for review
(`pytest`, fallback: `../../pytest/SKILL.md`).

## pytest

The root `testpaths` lists member roots for discovery only. Do not add a root
`pythonpath` listing every member; make shared test support importable per
member as described in `../../python-service-architecture/references/testing.md`
("Test support packages"). Async tests are native `async def` under the one
async plugin the repository already uses (anyio or pytest-asyncio); test design
belongs to the `pytest` skill.
