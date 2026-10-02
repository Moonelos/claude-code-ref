# Async Alembic Migrations

Alembic's default (`generic`) template calls `engine_from_config()`, which
does not understand async drivers (`asyncpg`, async `psycopg`). Use the
`async` template instead of hand-rolling the sync-to-async bridge:

```bash
alembic init -t async alembic
```

That scaffolds an `env.py` already wired for an async engine. If you're
retrofitting an existing `generic`-template project instead, apply the same
shape by hand — see the template below.

## `env.py`

```python
import asyncio
from logging.config import fileConfig
from typing import Final

from alembic import context
from sqlalchemy import Connection, pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

import db_models.models  # noqa: F401  registers every table on the metadata
from db_models.base import SQLModel

MIGRATION_LOCK_NAME: Final = "db-migrate"
MIGRATION_LOCK_TIMEOUT: Final = "60s"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        connection.execute(
            text("SELECT set_config('lock_timeout', :timeout, true)"),
            {"timeout": MIGRATION_LOCK_TIMEOUT},
        )
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:name))"),
            {"name": MIGRATION_LOCK_NAME},
        )
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async_migrations())
```

Things that are easy to get wrong here, in order of how often they bite:

- **Import the models before `target_metadata = SQLModel.metadata`.** This is
  the most common cause of "I added a model but `--autogenerate` produced an
  empty migration": nothing ever ran the module that defines it, so it never
  attached itself to the metadata Alembic diffs against.
- **Serialize runs.** The transaction-scoped advisory lock with a bounded
  `lock_timeout` makes two concurrent runners (two deploys, a retried job)
  queue or fail instead of interleaving. It is released at commit. With
  `transaction_per_migration=True`, take a session-level `pg_advisory_lock`
  on the connection instead and unlock in `finally`. Keep a test that starts
  two runners and asserts they can't overlap.
- **`poolclass=pool.NullPool` on the migration engine only.** A migration run
  is a one-shot process (`engine-and-session.md`); the app engine must not use
  `NullPool`.
- **`compare_type=True, compare_server_default=True`.** Type comparison is on
  by default in current Alembic; server-default comparison is not. Set both
  explicitly so the drift policy is visible.

## `alembic.ini`

Leave `sqlalchemy.url` blank or pointing at a placeholder — never commit a
real connection string. `env.py` is a process entry point: near the top, before
the online/offline branch, it loads the migration process's own secrets model
(`MigrationSecrets`, only `database_dsn`; `python-settings-config`, fallback
`../../python-settings-config/references/secrets-py.md`) and never the
service's `Settings`, so migrating needs no other service variables:

```python
secrets = MigrationSecrets()
config.set_main_option(
    "sqlalchemy.url", secrets.database_dsn.get_secret_value().replace("%", "%%")
)
```

`script_location` points at wherever `alembic/` actually lives per
`references/repo-layout.md` — colocated under `db/alembic/`
in a single-service repo, or inside the dedicated migration-runner service
(`services/db-migrate/alembic/`) in a monorepo — never inside the shared
models package itself, which stays free of an `alembic` dependency.

The `.replace("%", "%%")` matters: `sqlalchemy.url` passes through
ConfigParser interpolation, and a generated password containing `%` breaks it
with a baffling `InterpolationSyntaxError` long after everything worked in dev.

An `alembic/` directory inside the import package (`db/alembic/`) needs
`__init__.py` in `alembic/` and `versions/` to satisfy Ruff `INP001`, or a
per-file ignore for that directory.

## Day-to-day workflow

```bash
alembic revision --autogenerate -m "add users.last_login_at"
alembic upgrade head
alembic downgrade -1
```

Always open the generated revision file and read it before committing.
Two autogenerate artifacts to fix by hand every time:

- **Application column types leak into revisions.** Autogenerate renders a
  custom type such as `StrEnumText(ClaimStatus)` as an import of application
  code, so the migration changes whenever the model does. Render it as the
  storage type: `sa.Text()` plus the named CHECK with its values frozen as
  literals in the revision. Do it once with a `render_item` hook in `env.py`
  that returns `"sa.Text()"` for the custom type, instead of editing each file.
- **Expression and functional indexes show false drift.** PostgreSQL stores
  the expression in its normalized form, so `alembic check` reports a change
  that is not one. Write the index expression in the form PostgreSQL returns
  (`pg_get_indexdef`) so they compare equal, or exclude that one named index
  from comparison with an `include_object` hook and pin it with a
  schema-verification test (`schema-verification.md`) instead.

Autogenerate is a diff against structure, not intent. Data work is written
by hand ("Data backfills are written, never generated" below), and even with
`compare_type`/`compare_server_default` on, some changes (renaming a column
vs. drop+add, some enum/check-constraint edits) still need a hand-adjusted
migration rather than the generated one taken as-is.

One Alembic history serves one `target_metadata`; where it lives and why it
is never split per service is in `references/repo-layout.md` ("Why migrations
are never split per service").

Continuous proof that the history and the models actually agree — the
database-contract CI job, `alembic check`, parity tests, and pinning the
schema objects autogenerate can't see — is its own topic:
`references/schema-verification.md`.

## Transaction semantics: know what rolls back

With the `env.py` above, one `alembic upgrade` run executes **all** pending
revisions inside a single transaction (Postgres has transactional DDL). A
failure anywhere — including in the last of ten revisions — rolls the whole
run back: the database ends exactly where it started, `alembic_version`
included. That's the property you reason with during an incident: "the
migration task exited 1" means *nothing was applied*, not "it's somewhere in
the middle". Alembic's `transaction_per_migration=True` option changes that
to one transaction per revision — earlier revisions then stay applied when a
later one fails. Pick one deliberately and leave it alone; flipping it
changes what a failed deploy leaves behind.

The exception that breaks the single-transaction world: statements Postgres
refuses to run inside any transaction, most famously
`CREATE INDEX CONCURRENTLY`. Those need an explicit autocommit island:

```python
with op.get_context().autocommit_block():
    op.create_index(..., postgresql_concurrently=True)
```

and a revision containing one loses the all-or-nothing rollback for that
statement — keep such revisions minimal and idempotent-minded
(`IF NOT EXISTS`), because a failure can now leave them half-applied.

## Data backfills are written, never generated

Autogenerate diffs structure; it will never write the UPDATE that populates a
new NOT NULL column or reshapes existing rows. When a revision needs data
work:

- Do it with `op.execute` / `sa.table()` lightweight constructs, **not** by
  importing application models or live model constants (enum members,
  defaults). Those describe *today's* schema; inline a frozen copy of the
  values instead, or the migration breaks the moment the model evolves.
- The additive-column pattern: add nullable (or with a server default) →
  backfill → then tighten to NOT NULL, in that order, so the table is never
  invalid mid-flight.
- A backfill that touches millions of rows doesn't belong in the deploy-path
  migration at all — one giant UPDATE takes one giant lock. Batch it, or ship
  it as a separate one-off job and let the migration only flip constraints
  once the data is verifiably there.

## One head, even with many authors

Two branches that each add a revision merge into a history with two heads,
and `alembic upgrade head` refuses to guess. Catch it in CI with the
single-head test under "Migration tests", and repair with a merge revision (`alembic merge -m "merge" <rev1> <rev2>`)
or by re-parenting the newer branch's `down_revision`. The monorepo layout
already minimizes this (one place can generate revisions), but it cannot
prevent two PRs racing.

## Runner commands

The migration runner exposes three commands and nothing else is needed to
operate it: `upgrade` (`alembic upgrade head`), `check` (`alembic check`,
used by CI and before deploys) and `sql` (`alembic upgrade head --sql`, the
offline script for DBA review). All run with the `env.py` settings above.

## Writing revisions

- **Naming:** the metadata naming convention (`models-and-base.md`) names
  every PK/FK/UQ/CK/IX; revisions refer to names through `op.f()`. Hand-name
  only what the convention can't express.
- **Revision ids** are `YYYYMMDD_NNNN` via `alembic revision --rev-id`, with
  `file_template = %%(rev)s_%%(slug)s` so files read
  `YYYYMMDD_NNNN_<slug>.py`. Keep the id itself short: `alembic_version.version_num`
  is `VARCHAR(32)`.
- **`script.py.mako` follows house style:** PEP 604 unions,
  `collections.abc`, and typed module attributes:

  ```mako
  from collections.abc import Sequence

  revision: str = ${repr(up_revision)}
  down_revision: str | None = ${repr(down_revision)}
  branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
  depends_on: str | Sequence[str] | None = ${repr(depends_on)}
  ```

- Use one SQLAlchemy type per concept across revisions (`sa.Uuid()`,
  `sa.DateTime(timezone=True)`, `sa.func.now()`).
- **Check data before tightening constraints.** Before adding NOT NULL, a
  CHECK or a unique constraint, query for violations and fail with example
  keys and an operator instruction, instead of letting the DDL fail opaquely.
- A backfill's temporary `server_default` is dropped after the backfill,
  unless the model declares it permanently.
- **Every `downgrade()` is an exact inverse**, or raises deliberately with an
  operator-facing reason. A downgrade never silently loses data.
- After a feature removal, file the contract (drop) migration for the next
  release, and remove dialect variants nothing uses any more.

## Migration tests

Call Alembic `command.*` from async tests through `asyncio.to_thread`, since
`env.py` runs its own event loop. Test placement follows
`../../python-service-architecture/references/testing.md` (Profiles and markers).

```python
from alembic.config import Config
from alembic.script import ScriptDirectory

from myservice.db.schema import EXPECTED_SCHEMA_REVISION


def test_history_has_a_single_head(alembic_config: Config) -> None:
    assert len(ScriptDirectory.from_config(alembic_config).get_heads()) == 1


def test_code_expects_the_current_head(alembic_config: Config) -> None:
    assert ScriptDirectory.from_config(alembic_config).get_current_head() == EXPECTED_SCHEMA_REVISION
```

Both are DB-free. Never count revision files; other tests reference
`EXPECTED_SCHEMA_REVISION`, never a literal revision id.

## A fresh database replays the entire history

`alembic upgrade head` on an empty database runs every revision ever written,
in order. Two consequences that only surface at the worst moment — the first
real deployment:

- **A migration that can fail closed blocks fresh installs by design.** A
  destructive contract migration guarded by an operator gate (an env-var
  readiness flag, an in-transaction preflight) is correct protection for a
  *live* database — but a brand-new environment replays it too, and the gate's
  default is "refuse". When writing such a gate, decide explicitly what a
  fresh install does: either the history is squashed before anything deploys
  (below), or every fresh-install surface (local compose, CI, each new
  environment's deploy path) must be wired to satisfy the gate, *documented in
  the rollout runbook, not discovered from the traceback*. A gate whose error
  message names a command is a contract: the command must exist.
- **Expand/contract pairs are pure waste on an empty database** — it builds
  the old tables just to drop them. Tolerable as history; a smell when the
  history has never been deployed anywhere.

### Squash to a baseline before the first deployment

While no deployed environment exists, the migration history is a development
artifact — no database sits on an intermediate revision, so nothing entitles
it to survive. Before the first real deployment, squash it to a single
baseline revision. After first deployment it's too late: squashing then
requires re-stamping or restoring every live database.

The procedure, each step earning its keep:

1. Apply the **old full history** to scratch database A (satisfy any gates —
   trivially true on an empty database); `pg_dump --schema-only` it.
2. Delete every revision file, then `alembic revision --autogenerate -m
   "baseline schema"` against empty scratch database B. This captures exactly
   what `target_metadata` describes — and **nothing else**.
3. **Hunt for schema objects that live outside the metadata.** Anything a
   revision created via `op.execute` — triggers, functions, extensions, RLS
   policies, grants — is invisible to autogenerate and silently absent from
   the generated baseline. Grep the old revisions for `op.execute` and carry
   those statements into the baseline by hand.
4. Prove it: apply the baseline to scratch database B, dump, and diff the two
   dumps normalized (strip comments and pg_dump's `\restrict` nonce lines;
   compare order-insensitively — column order legitimately differs when late
   `ADD COLUMN`s fold into the baseline's metadata order). The diff must be
   empty. `alembic check` against B must also be clean.
5. Sweep for **pinned revision ids outside `alembic/`**: runtime
   schema-version guards (a service asserting `alembic_version` at startup),
   tests naming revisions, docs, runbooks. The baseline gets a new id; every
   pin moves with it.
6. Retire the machinery the squash obsoletes in the same change: gate env
   vars in compose/CI/conftests/IaC variables, preflight scripts and their
   `[project.scripts]` aliases, runbook sections for rollouts that will now
   never run. Give the baseline `downgrade()` a deliberate `raise` — below
   the baseline there is nothing but dropping every table; rollback is a
   database restore.

A revision-count threshold is not the trigger; **"has anything deployed yet?"
is.** One deployed environment on the history means no squash — write a
normal forward migration instead.

## The rollout runbook: one file, head only

Once migrations gate on operator action — a preflight to review, an
env-var attestation, an expand/contract sequenced against deploys,
irreversible DDL — the rollout procedure needs a home, and that home has
rules learned the hard way:

- **Exactly one runbook file** in the migration-runner service, describing
  the rollout of whatever is *currently at head*. Never one file per
  migration: per-migration docs accumulate, go stale, and eventually two of
  them contradict each other about the same database. When a migration's
  rollout has fully shipped everywhere and gates nothing, delete its section
  — history belongs to `git log`.
- **Every command the runbook tells an operator to run must exist**, as a
  `[project.scripts]` entry whose behavior matches the prose — and the same
  goes for commands named in a migration's *error messages*. A gate that
  fails with "run `foo-preflight` first" when no such command exists strands
  the operator at the worst possible moment. Retiring a gate retires its
  script alias and its runbook section in the same change.
- **The gate variable named in the runbook is the one the migration actually
  checks** — a rename on either side without the other produces instructions
  that can't work.
- Downgrade guidance is part of the entry: either the real inverse, or an
  explicit "restore the backup" with `downgrade()` raising — never a
  synthesized reconstruction of dropped data.
