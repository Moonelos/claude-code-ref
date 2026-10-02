# Executable fixture tests

Run from `python-service-architecture/`:

```bash
# Persistence: the store against disposable SQLite files
PYTHONPATH=assets/canonical_service/src uv run --no-project \
  --with "sqlalchemy[asyncio]" --with sqlmodel --with aiosqlite \
  python -B -m unittest discover -s assets/canonical_service/tests/integration

# HTTP translation: routes and the public error table over a runtime of fakes
PYTHONPATH=assets/canonical_service/src uv run --no-project \
  --with "sqlalchemy[asyncio]" --with sqlmodel --with fastapi --with httpx \
  --with pydantic-settings \
  python -B -m unittest discover -s assets/canonical_service/tests/unit
```

The integration tests use disposable SQLite files to exercise uniqueness,
concurrent submission, rollback and error translation. The unit tests override
`get_runtime` and the identity dependency, so no lifespan, database, or
authentication middleware runs. Both are separate from the auditor's
stdlib-only regression suite. They do not prove PostgreSQL locking or isolation:
run concurrency tests against the production engine before adopting the example.
The duplicate handler assumes READ COMMITTED when used with PostgreSQL.
