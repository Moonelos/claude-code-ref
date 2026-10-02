# Dockerfile Entrypoint: Monorepo vs. Single-Service

Follows the multi-stage shape from `python-repository-setup`'s
`../../python-repository-setup/references/docker-builds.md` (uv stage → python-base → builder → runtime,
`.venv` copied into runtime, non-root numeric user, `tini` as the process
entrypoint). This file only covers the one piece that's specific to running
migrations: what the runtime stage's `ENTRYPOINT`/`CMD` should be, and how
that differs between the two repo shapes in `references/repo-layout.md`. The
two cases differ for the same reason the folder layout does; the table at the
end compares them.

## Monorepo — `services/db-migrate/Dockerfile`

```dockerfile
# ... same uv / python-base / builder stages as any other workspace member ...
# builder: uv sync --locked --no-dev --no-editable --package db-migrate

FROM python-base AS runtime
COPY --from=builder /app/.venv /app/.venv
COPY services/db-migrate/alembic.ini services/db-migrate/alembic.ini
COPY services/db-migrate/alembic services/db-migrate/alembic
WORKDIR /app/services/db-migrate
USER 10001:10001
ENTRYPOINT ["tini", "--"]
CMD ["/app/.venv/bin/alembic", "upgrade", "head"]
```

- `alembic.ini` and `alembic/` are `COPY`'d explicitly, not baked into the
  wheel — per `docker-builds.md`: *"Copy migrations or external configuration
  separately only when they intentionally remain outside the installed
  package."* Migrations are exactly that case.
- `WORKDIR` is set to wherever `alembic.ini` was copied to, so the bare
  `alembic upgrade head` finds it without a `-c` flag.
- The alembic invocation is the container's `CMD`, not baked into
  `ENTRYPOINT` — `tini` stays the entrypoint (correct signal handling for a
  short-lived task), and only the `CMD` array is what a one-off run
  overrides. That's what makes `alembic downgrade -1` or `alembic history`
  for debugging a plain command-array override at the orchestration layer,
  never a rebuild.
- No other service (`api`, `worker`, …) ever copies `alembic.ini` or installs
  `alembic` — this image is the only place that dependency exists at all
  (`references/repo-layout.md`).

## Single-service repo — root `Dockerfile`

One image total; its default `CMD` runs the application:

```dockerfile
FROM python-base AS runtime
COPY --from=builder /app/.venv /app/.venv
COPY src src
COPY alembic.ini alembic.ini
WORKDIR /app
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["tini", "--"]
CMD ["/app/.venv/bin/uvicorn", "myservice.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Running migrations means overriding just the command, same image, same
`ENTRYPOINT`:

```bash
/app/.venv/bin/alembic upgrade head
```

`WORKDIR` is already `/app`, and `alembic.ini` was copied to `/app/alembic.ini`
— alembic finds it in the current directory with no `-c` flag needed, exactly
like the monorepo case, just at a different path.

## The difference, side by side

| | Monorepo (`db-migrate`) | Single-service |
|---|---|---|
| How many images | A dedicated one, only for migrations | One, shared with the app |
| Default `CMD` | `alembic upgrade head` | the app server |
| How a migration run happens | The default — the image does nothing but run migrations | A one-off `CMD` override of the same image at task-run time, never a separate build |
| `ENTRYPOINT` | `["tini", "--"]` | `["tini", "--"]` — only the `CMD` array ever changes |
| Who has `alembic` installed | Only `db-migrate` | The one and only service (unavoidable — there's nothing else to keep it out of) |
