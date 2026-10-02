# `pyproject.toml` Files

Concrete `pyproject.toml` shapes for each repository mode. The rules that decide
*which* file owns *what* live in `../SKILL.md`; the root files are the
templates' (linked below), whose tool tables are explained in
[quality-tooling.md](quality-tooling.md).

## Root `pyproject.toml`

### Single-service project

For one deployable, the root is an ordinary installable project. Put runtime
dependencies in root `[project.dependencies]`, development tools in the root
`dev` dependency group, and source in `src/<import_package>/`. Keep one root
`uv.lock`; do not add `[tool.uv.workspace]` or use `--package`.

The complete file is
[../assets/single-service-template/pyproject.toml](../assets/single-service-template/pyproject.toml):
`[project]` with `requires-python` and the runtime dependencies, a hatchling
`[build-system]`, `[tool.uv] required-version`, the `dev` group (`import-linter`,
`mypy`, `pre-commit`, `pytest`, `pytest-cov`, `ruff`), and the shared Ruff,
pytest, coverage, mypy, and import-linter tables already set to the
single-service roots (`src`, `tests`).

### Workspace virtual root and shared tooling

The complete file is
[../assets/workspace-template/pyproject.toml](../assets/workspace-template/pyproject.toml):
`[tool.uv] required-version`, `[tool.uv.workspace] members` as globs
(`services/*`, `libs/*`), the same `dev` group as the single-service template
(`import-linter`, `mypy`, `pre-commit`, `pytest`, `pytest-cov`, `ruff`; the two
are checked equal by `../tests/test_templates.py`), and the Ruff, pytest,
coverage, mypy, and import-linter tables.

uv supports a root with no `[project]` table at all — a "virtual" workspace
root, for which nothing is built or installed. What it may hold is ruled in
`../SKILL.md` ("`pyproject.toml` Ownership"). In particular, do not add root
`[project]`, `[project.dependencies]`, or `[build-system]` merely to express
Python compatibility; put `requires-python` on every installable member.

## Service `pyproject.toml`

```toml
[project]
name = "api"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
    "fastapi",
    "uvicorn",
    "company-observability",
]

[tool.uv.sources]
company-observability = { workspace = true }

[build-system]
requires = ["hatchling>=1.32.0,<2"]
build-backend = "hatchling.build"
```

```toml
[project]
name = "worker"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
    "boto3",
    "company-observability",
]

[tool.uv.sources]
company-observability = { workspace = true }

[build-system]
requires = ["hatchling>=1.32.0,<2"]
build-backend = "hatchling.build"
```

`workspace = true` tells uv to satisfy `company-observability` from
`libs/company_observability/` instead of PyPI, and installs it editable. Each
service declares only what it imports — `api` never sees `boto3`, `worker`
never sees `fastapi`.

Give every workspace member a `src/<package>/` layout with the import package
matching the project name with hyphens replaced by underscores
(`company-observability` → `src/company_observability/`). Hatchling
autodetects that layout with no extra `[tool.hatch.build.targets.wheel]`
config; add `packages = ["src/<package>"]` explicitly only if autodetection
fails (for example, a project name that doesn't normalize to the directory
name).

## Shared Library `pyproject.toml`

```toml
[project]
name = "company-observability"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp-proto-http",
    "structlog",
]

[build-system]
requires = ["hatchling>=1.32.0,<2"]
build-backend = "hatchling.build"
```

A shared library is a workspace member exactly like a service — it gets its
own `pyproject.toml`, its own dependencies, and is consumed by
`{ workspace = true }` from whichever services import it. It does not need to
know which services depend on it. The observability dependency list above is an
example, not a default for other libraries.
