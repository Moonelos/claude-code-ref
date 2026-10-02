# Setup And Verification

Run after adapting a template, and after changing hooks, members, pins, or
images. Run every command from the repository root unless noted.

## Environment and quality gate

Single deployable:

```bash
uv python install
uv lock --check
uv sync --frozen
uv run --locked pre-commit validate-config
uv run --locked pre-commit install
uv run --locked pre-commit run --all-files --hook-stage pre-commit
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
uv run --locked pre-commit run --all-files --hook-stage pre-push
uv sync --frozen --no-dev
```

Workspace: the same sequence, except that the root is virtual, so a plain
`uv sync --frozen` installs no members. Sync every member, type-check per
member, and prove each deployable's scoped closure:

```bash
uv python install
uv lock --check
uv sync --frozen --all-packages
uv run --locked pre-commit validate-config
uv run --locked pre-commit install
uv run --locked pre-commit run --all-files --hook-stage pre-commit
uv run ruff check .
uv run ruff format --check .
scripts/mypy-members.sh
uv run pytest
uv run --locked pre-commit run --all-files --hook-stage pre-push
uv sync --frozen --no-dev --package <service>
```

The scoped `--package` sync is the real test of a member's dependency boundary
([workspace-rationale.md](workspace-rationale.md#the-shared-dev-environment-is-not-a-dependency-firewall));
re-run `uv sync --frozen --all-packages` afterwards to restore the shared
development environment.

Then run the repository's CI-equivalent commands that are not owned by the
hook stages. Confirm:

- repeated runs are clean and do not keep modifying files;
- hook revisions match the selected uv/Ruff versions;
- local hooks resolve through the locked workspace environment;
- every current Python root is covered by the intended lint/type/test scope;
- skipped integration/live/deployment checks have a separate enforced CI owner;
- a fresh checkout can run the hooks without undeclared developer-global tools,
  except explicitly documented `language: system` prerequisites.

## Toolchain

Run the toolchain check from this skill package before copying the asset;
after copying, use the remaining checks from the generated repository root:

```bash
python scripts/update_toolchain.py --check
test "$(uv run python -c 'import platform; print(platform.python_version())')" = "$(tr -d '\r\n' < .python-version)"
uv --version
```

The expected owner of each pin is in [toolchain.md](toolchain.md#final-ownership).

## Docker image

Build from the repository root. Workspace:
`docker build --pull -f services/<service>/Dockerfile -t <service>:local .`;
single service: `docker build --pull -f Dockerfile -t <service>:local .`. For
the workspace template's `api` service:

```bash
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

## Compose stack

```bash
docker compose config --quiet
docker compose up --build
```

Verify missing substitutions fail, required variables reach the intended
container, unrelated service secrets remain absent, and startup validation
succeeds. Do not print secret values during validation.
