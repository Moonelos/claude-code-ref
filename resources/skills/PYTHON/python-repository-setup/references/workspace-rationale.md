# Why a uv Workspace, and What It Does Not Guarantee

Background for the rules in `../SKILL.md`. Read it when a user asks why the
repository is split into members, or doubts that scoped installs matter.

## Why not one root `pyproject.toml`

A single shared dependency list forces every service to install every other
service's dependencies. A worker that only needs `boto3` and `celery` still
ships `fastapi` and `uvicorn` because the API service declared them in the same
file. This is invisible at small scale and gets worse as services and
dependencies accumulate: every Docker image grows, every image rebuild
reinstalls unrelated packages, and `uv add <pkg>` for one service silently
changes what every other service resolves and ships.

A uv workspace fixes this without giving up a single, consistent dependency
resolution: each service and library keeps its own dependency list, but uv
still resolves the whole workspace into one lockfile and can scope an install
to exactly one member's dependency closure.

## Observed uv behavior

- `uv sync --package api` installed `api` and `company-observability`, and left
  `worker` out entirely.
- `uv sync --package api` alone still installed a root-level `dev` dependency,
  which is why shipped builds always add `--no-dev`.

## The shared dev environment is not a dependency firewall

uv's documentation says so explicitly: *"uv can't ensure that packages don't
import dependencies declared by another workspace member."* A stray
`import worker` inside `api`'s source runs fine in the shared dev environment
and only fails once something does a `--package`-scoped install, such as a
production Docker build or CI. "It works locally" is not proof of a clean
dependency boundary.
