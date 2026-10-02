# Schema Verification: Making "Migrations Match Models" a Guarantee

Autogenerate review (`references/alembic-migrations.md`) catches drift at the
moment a revision is written. Everything in this file exists because drift
also happens *between* those moments — a model edited without a migration, a
migration hand-tweaked without the model, a trigger added that nothing tracks.
Left unverified, the failure mode is a database that `alembic upgrade head`
builds *almost* like the models describe, discovered by a worker crashing on
a column that isn't there.

## The standing harness: a database-contract CI job

One CI job, running on every PR, against a disposable Postgres service
container (same major version as production — reflection output differs
across versions):

1. **Apply the real history**: `alembic upgrade head` against the empty
   scratch database. Not `metadata.create_all()` — the point is to exercise
   the migrations, and `create_all()` is exactly the shortcut that lets them
   rot.
2. **Diff models against the result**: `alembic check` — it exits non-zero
   and prints the pending operations when `target_metadata` and the migrated
   database disagree. This one step is what turns "upgrade head produces
   exactly what the models describe" from a hope into an invariant.
3. **Run the DB-touching test tiers** against that same migrated database, in
   a declared order when fixtures disagree about who owns the schema.

Also in this job, when the deployment supports it:

- Upgrade from each operationally supported prior release snapshot to head,
  not only from blank.
- The DB-free single-head and expected-revision tests
  (`alembic-migrations.md`, "Migration tests") prove the history has one head
  and that the code pins it.
- Test downgrade only when operational rollback is supported; do not add a
  ceremonial downgrade test for a one-way migration policy.
- Migration tests share one throwaway-database fixture. Run the migration tool
  either in process (`command.*` through `asyncio.to_thread`, per
  `alembic-migrations.md`) or as a subprocess through one helper with a
  timeout, for example in the two-runner serialization test.

Alongside the CI diff, keep one integration test module that asserts parity
structurally, so a failure names the exact table/column/constraint instead of
dumping an autogenerate op list:

```python
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlmodel import SQLModel


def test_no_model_to_database_drift(sync_connection: Connection) -> None:
    diffs = compare_metadata(
        MigrationContext.configure(
            sync_connection,
            opts={"compare_type": True, "compare_server_default": True},
        ),
        SQLModel.metadata,
    )
    assert diffs == []
```

plus reflection-based assertions (via `sqlalchemy.inspect`) that the
database contains **only** the expected tables (`alembic_version` included),
and that names of PKs/FKs/uniques/checks/indexes — and the `postgresql_where`
predicates of partial indexes — match the metadata. Reflection catches what
`compare_metadata` is configured to ignore. A consumer whose column contract
spans a shared schema compares reflected column **types**, not only names.

## Schema objects that live outside the metadata

Anything a revision creates via `op.execute` — triggers, functions,
extensions, row-level-security policies, grants — is invisible to
autogenerate **and** to `alembic check`. From the moment such an object is
written, nothing above verifies it exists. So the rule is: the same change
that adds an `op.execute` object also adds its pin —

- a behavioral integration test (e.g. an UPDATE that the trigger must
  reject), and/or
- a reflection/catalog assertion (query `pg_trigger`/`pg_proc`, or a
  normalized `pg_dump --schema-only` comparison) that the object is present
  after `upgrade head`.

This is also why squashing history requires a dump diff, not just
`alembic check` (`references/alembic-migrations.md`) — the metadata-based
tools would happily bless a baseline that silently dropped every trigger.

## Runtime schema-version guard

A service can assert at startup (or in its readiness check) that the database
it connected to is at the revision its code was built against:

```python
# db/schema.py
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

EXPECTED_SCHEMA_REVISION: Final = "20260927_0001"


class SchemaRevisionMismatchError(Exception):
    def __init__(self, *, expected: str, actual: str | None) -> None:
        super().__init__(f"database schema is at {actual!r}, code expects {expected!r}")
        self.expected = expected
        self.actual = actual


async def verify_schema_revision(conn: AsyncConnection) -> None:
    actual = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    if actual != EXPECTED_SCHEMA_REVISION:
        raise SchemaRevisionMismatchError(expected=EXPECTED_SCHEMA_REVISION, actual=actual)
```

It fails fast and legibly on deployment skew — an old image against a
migrated database, or a new image racing the migration task — instead of
failing later on a missing column. The cost is real and must be owned: every
new revision bumps the constant in **every** service that pins it, in the
same change as the migration. The DB-free head test in
`alembic-migrations.md` ("Migration tests") catches a stale pin before merge.
(This is the same "pinned revision ids outside `alembic/`" sweep the squash
procedure requires.)

## Disposable test databases

Fixture mechanics and placement are owned by
`../../python-service-architecture/references/testing.md` (Profiles and
markers; Test support packages). The DB-specific guard:

- DB-touching tests that rebuild the schema read their target from a
  **separate** variable, `INTEGRATION_<DB>_DATABASE_URL` (e.g.
  `INTEGRATION_ORDERS_DATABASE_URL`), never the service's `DATABASE_URL`.
  Setting it *is* the authorization to destroy the target.
- The fixture **refuses non-disposable targets**: a non-loopback host, or a
  database name without the `test_` prefix, fails the session before any
  statement runs. CI's throwaway service container uses a name that passes
  (`postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/test_orders`).
- When the variable is unset, the tests **fail** in CI profiles
  (`REQUIRE_INTEGRATION=1`, through pytest's `require_env` helper:
  `../../pytest/references/examples-core.md`, "Profile prerequisites") and skip
  only in local runs, so
  a CI misconfiguration can't turn the whole DB tier green by skipping it.
- Each service's fixtures drop and rebuild only the schemas that service owns
  (`repo-layout.md`, "Schema ownership and prototype mode"), never
  `DROP SCHEMA public CASCADE` on a schema another owner migrates.
