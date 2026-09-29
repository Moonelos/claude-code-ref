# `pyproject.toml` Files

Concrete `pyproject.toml` shapes for each repository mode. The rules that decide
*which* file owns *what* live in `../SKILL.md`; the Ruff, pytest, coverage and
mypy tables are in
[../assets/workspace-template/pyproject.toml](../assets/workspace-template/pyproject.toml).

## Root `pyproject.toml`

### Single-service project

For one deployable, the root is an ordinary installable project. Put runtime
dependencies in root `[project.dependencies]`, development tools in the root
`dev` dependency group, and source in `src/<import_package>/`. Keep one root
`uv.lock`; do not add `[tool.uv.workspace]` or use `--package`:

```toml
[project]
name = "my-service"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = ["fastapi", "uvicorn"]

[dependency-groups]
dev = [
    "mypy>=2.3.0,<3",
    "pre-commit>=4.6.1,<5",
    "pytest>=9.1.1,<10",
    "pytest-cov>=7.1.0,<8",
    "ruff>=0.16.3,<0.17",
]

[build-system]
requires = ["hatchling>=1.32.0,<2"]
build-backend = "hatchling.build"
```

The complete file, with the shared Ruff, pytest, coverage, mypy, and
import-linter tables already set to the single-service roots (`src`, `tests`),
is [../assets/single-service-template/pyproject.toml](../assets/single-service-template/pyproject.toml).

### Workspace virtual root and shared tooling

```toml
[tool.uv]
required-version = "==0.12.7"

[tool.uv.workspace]
members = [
    "services/*",
    "libs/*",
]

[dependency-groups]
dev = [
    "mypy>=2.3.0,<3",
    "pre-commit>=4.6.1,<5",
    "pytest>=9.1.1,<10",
    "pytest-cov>=7.1.0,<8",
    "ruff>=0.16.3,<0.17",
]
```

The Ruff, pytest, coverage, and mypy tables live in the same file; copy them
from [assets/workspace-template/pyproject.toml](../assets/workspace-template/pyproject.toml).

uv supports a root with no `[project]` table at all — this is a "virtual"
workspace root: nothing is built or installed for the root itself, it only
groups members, anchors the single `uv.lock`, pins uv, and configures shared
development tools. Keep repo-wide lint, test, coverage, and type-check tools in
the root `dev` group. Keep framework-specific test plugins or type stubs used
by only one member in that member's own dependency group.

Do not add root `[project]`, root `[project.dependencies]`, or a root
`[build-system]` merely to express Python compatibility. Put
`requires-python` on every installable workspace member instead.

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
