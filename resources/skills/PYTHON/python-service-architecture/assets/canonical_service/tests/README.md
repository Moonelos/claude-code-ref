# Executable persistence fixture

Run from `python-service-architecture/`:

```bash
PYTHONPATH=assets/canonical_service/src uv run --no-project \
  --with "sqlalchemy[asyncio]" --with sqlmodel --with aiosqlite \
  python -B -m unittest discover -s assets/canonical_service/tests/integration
```

These tests use disposable SQLite files to exercise uniqueness, concurrent
submission, rollback and error translation. They are separate from the auditor's
stdlib-only regression suite. They do not prove PostgreSQL locking or isolation:
run concurrency tests against the production engine before adopting the example.
The duplicate handler assumes READ COMMITTED when used with PostgreSQL.
