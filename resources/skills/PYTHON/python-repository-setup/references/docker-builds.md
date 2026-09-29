π

# Production Docker Builds

## Contents

- Version contract
- Build context and dependency metadata
- Required multi-stage shape
- Sync flags
- `.dockerignore`
- Service variants
- Validation

Copy the canonical files; do not rewrite the pattern from memory. Workspace:
`../assets/workspace-template/services/api/Dockerfile`. Single service:
`../assets/single-service-template/Dockerfile`. Both use the same
`.dockerignore`, and their base and runtime stages are identical (checked by
`../tests/test_templates.py`).

## Single-service adaptation

The single-service template already applies this. Build a root `Dockerfile`
with `.` as its context. Copy the root
`pyproject.toml`, `uv.lock`, and `.python-version` for the dependency layer,
then copy `src/` before the final install. Because the root is the installable
project, omit workspace-member metadata and do not use `--package` or
`--no-install-workspace`:

```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable
```

Keep the version check, builder/runtime split, identical `/app` path, numeric
non-root runtime user, `tini`, health-check policy, and runtime-secret boundary
from the workspace image. Validate with `docker build --pull -f Dockerfile .`.

## Version Contract

Keep these version surfaces aligned:

```text
.python-version                         3.13.15
member requires-python                  >=3.13,<3.14
Docker ARG PYTHON_VERSION               3.13.15
root [tool.uv] required-version         ==0.12.7
Docker ARG UV_VERSION                   0.12.7
```

The exact Python patch belongs in `.python-version`, Docker, and CI. The member
metadata uses a compatible minor range because it describes package
compatibility rather than selecting an interpreter. Put the same range on
every service and library; a virtual workspace root has no `[project]` table.

Do not add mise. Locally, let uv read `.python-version`; run `uv python install`
when the interpreter is absent. Pin uv in the root so the wrong local version
fails immediately, and install that exact version in CI.

Docker evaluates `FROM` before it can `COPY` `.python-version`. Therefore it
cannot dynamically derive `ARG PYTHON_VERSION` from that file. Repeat the
literal exact version and add this early builder check:

```dockerfile
ARG PYTHON_VERSION
COPY .python-version ./
RUN test "$(tr -d '\r\n' < .python-version)" = "${PYTHON_VERSION}"
```

When invoking Docker from a wrapper or CI shell, deriving the build argument
from the file is also valid:

```bash
docker build \
  --build-arg PYTHON_VERSION="$(tr -d '\r\n' < .python-version)" \
  -f services/api/Dockerfile .
```

Keep the Dockerfile default and the in-build equality check even when the
wrapper supplies the argument.

## Build Context And Dependency Metadata

Build from the workspace root:

```bash
docker build --pull -f services/api/Dockerfile -t sample-api:local .
```

Do not build with `services/api` as the context. uv needs the root
`pyproject.toml`, root `uv.lock`, `.python-version`, the target member's
metadata and source, and every internal library in its transitive dependency
closure.

For the dependency layer, copy the root files and every workspace member
`pyproject.toml` required to validate the shared lock before copying source:

```dockerfile
COPY .python-version pyproject.toml uv.lock ./
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY libs/sample_shared/pyproject.toml libs/sample_shared/pyproject.toml
```

If the root `members` globs include additional members, either copy all member
metadata for strict `--locked` validation or use a generated metadata-copy
stage. Do not hide a stale lock with `--frozen` merely because required member
metadata was omitted.

## Required Multi-Stage Shape

Use these stages:

1. `uv`: exact `ghcr.io/astral-sh/uv:${UV_VERSION}` binary source.
2. `python-base`: exact `python:${PYTHON_VERSION}-slim-trixie` shared by builder
   and runtime.
3. `builder`: install locked third-party dependencies, then install the target
   service and its internal dependency closure non-editably.
4. `runtime`: install only small OS runtime requirements, copy `.venv`, switch
   to a numeric non-root user, and start through `tini`.

Keep `/app` identical in builder and runtime because virtual-environment
scripts can contain absolute interpreter paths. Do not copy uv into the final
runtime stage. Do not copy source separately after `uv sync --no-editable`;
the service and internal libraries are already installed into `.venv`.

Keep these builder settings:

```dockerfile
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1 \
    UV_PYTHON_DOWNLOADS=0
```

Use a BuildKit cache mount for `/root/.cache/uv`. Add compilers and development
headers only to the builder when a dependency lacks a wheel. Add only the
corresponding shared runtime libraries to the runtime stage.

## Sync Flags

Dependency-only cached layer:

```bash
uv sync --locked --no-dev --no-install-workspace --package sample-api
```

Final builder layer after copying service and internal-library source:

```bash
uv sync --locked --no-dev --no-editable --package sample-api
```

- `--locked`: fail if metadata and `uv.lock` disagree.
- `--no-dev`: exclude centralized Ruff, pytest, coverage, and mypy tooling.
- `--package`: include only the target service and its transitive workspace
  dependencies.
- `--no-install-workspace`: keep source packages out of the cached dependency
  layer.
- `--no-editable`: install immutable wheels suitable for production.

Never put service runtime dependencies in the root dev group. `--no-dev`
correctly removes tooling only when runtime dependencies remain in each
member's `[project.dependencies]`.

## `.dockerignore`

Always exclude `.venv`; it is platform-specific and must be recreated inside
the image. Exclude tests, caches, build output, VCS data, editor files, and
local secrets unless the package build genuinely needs one of them.

Do **not** exclude `.python-version`. It must be available for the Docker
version-alignment check. In particular, remove this old rule if present:

```dockerignore
.python-version
```

Use the canonical `.dockerignore` from the bundled asset.

## Service Variants

For a web service, keep `EXPOSE`, a cheap local `HEALTHCHECK`, and an explicit
server command. Configure equivalent readiness/liveness checks in the actual
orchestrator; the Docker health check does not replace them.

For a worker, remove `EXPOSE` and HTTP `HEALTHCHECK`, then use a module or
console-script command such as:

```dockerfile
CMD ["/app/.venv/bin/python", "-m", "sample_worker.main"]
```

Package static resources into the wheel and read them with
`importlib.resources`. Copy migrations or external configuration separately
only when they intentionally remain outside the installed package.

Never pass secrets through `ARG` or `ENV` during builds. Use BuildKit secret
mounts for private indexes and the deployment platform's secret store at
runtime.

## Validation

Run from the workspace root:

```bash
uv lock --check
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
scripts/mypy-members.sh
uv run pytest
docker build --pull -f services/api/Dockerfile -t sample-api:local .
docker run --rm --entrypoint python sample-api:local --version
docker run --rm --entrypoint id sample-api:local
docker run --rm -d --name sample-api -p 8080:8080 sample-api:local
```

Confirm the reported Python equals `.python-version`, `id` reports UID/GID
`10001`, the container becomes healthy, and the runtime image has no uv:

```bash
docker exec sample-api sh -c 'command -v uv >/dev/null; test $? -ne 0'
docker inspect --format '{{json .State.Health}}' sample-api
```

Stop and remove the named validation container after the check.
