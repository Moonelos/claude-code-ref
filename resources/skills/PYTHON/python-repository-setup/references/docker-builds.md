# Production Docker Builds

## Contents

- Single-service adaptation
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

The Python/uv pins, the in-build `.python-version` equality check, and the
`--build-arg PYTHON_VERSION` wrapper form are owned by
[toolchain.md](toolchain.md#local-ci-and-docker). Keep the `ARG` defaults and
the check exactly as the templates have them.

## Build Context And Dependency Metadata

Build from the workspace root:

```bash
docker build --pull -f services/api/Dockerfile -t sample-api:local .
```

Do not build with `services/api` as the context. uv needs the root
`pyproject.toml`, root `uv.lock`, `.python-version`, the target member's
metadata and source, and every internal library in its transitive dependency
closure. Scoping the context to the service directory is a common mistake that
breaks the build the moment the service depends on a shared library.

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
  The root `dev` group is installed by default even with `--package`, so a
  shipped build without `--no-dev` (or `--only-group <name>` for a narrower
  selection) silently loses the lean image.
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
server command. That launcher command owns the bind host and port; they are
never YAML keys (`python-settings-config`, fallback
`../../python-settings-config/SKILL.md`, Ownership). Configure equivalent
readiness/liveness checks in the actual orchestrator; the Docker health check
does not replace them.

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

Build, run, and inspect the image with the commands in
[verification.md](verification.md#docker-image): Python matches
`.python-version`, UID/GID `10001`, healthy, and no uv in the runtime image.
