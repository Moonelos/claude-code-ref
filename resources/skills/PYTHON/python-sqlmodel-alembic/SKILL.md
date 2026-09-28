---
name: python-sqlmodel-alembic
description: >-
  Scaffold or review an async PostgreSQL data layer built on SQLModel,
  SQLAlchemy and Alembic, or on psycopg directly. Use for table models and
  metadata, engines, pools and sessions, transactions and units of work,
  repositories and raw SQL, work queues and leases, external read-only
  databases, migrations and backfills, schema verification, or a dedicated
  migration runner in a uv workspace.
---

# Async DB Layer: SQLModel + Alembic

Everything in this layer is **async**: async engine, `AsyncSession`, async
repository methods, async Alembic `env.py`. The only sync code is the
`Connection` handed to a `run_sync` callback.

If the service uses psycopg directly (including LangGraph `AsyncPostgresSaver`),
follow `references/psycopg.md`.

```text
base.py + models    SQLModel tables, naming convention, column vocabularies
   ↑
alembic/            the one migration history for that metadata
   ↑
engine.py → session.py → transactions.py → repositories/ and named db/ modules
builder     factory      transaction helper,   entity reads/writes; leases,
(bootstrap  (bootstrap   UoWs                   retention, external reads
 calls it)   calls it)                          (optional: queries/*.sql)
```

`base.py` and the models describe the schema; `alembic/` versions it.
Everything from `engine.py` down is how one process talks to that schema.

## Resolve the repo shape first

This skill assumes you already know whether you're in a **uv workspace
monorepo** (multiple independently-deployable services, or a repo that will
grow into that) or a **single-service repo**. That decision — and the
`services/` vs `libs/`/`packages/` naming, workspace sources, per-member
`pyproject.toml` — belongs to the `python-repository-setup` skill, not
this one. Resolve that first if it isn't already settled; this skill only
adds where the *DB* pieces specifically go once the shape is decided. See
`references/repo-layout.md` for both trees.

## Reference routing

Load only what you're touching:

- `references/repo-layout.md` — monorepo vs. single-service trees, what is
  shared vs. per-service, schema ownership and prototype mode.
- `references/models-and-base.md` — naming convention, `TableBase`,
  timestamps, when to split model modules, status enums, JSON codecs, shared
  predicates and transitions.
- `references/engine-and-session.md` — engine builder and pool sizing, session
  factory, **transactions and the unit of work**, the DB failure contract,
  per-transaction limits.
- `references/repositories-and-queries.md` — where SQL lives, repositories,
  inline vs. packaged `.sql`, relationship loading, raw SQL safety, efficient
  reads and bulk writes.
- `references/work-queues.md` — claiming, leases and fenced writes, the
  database clock, retention and bulk maintenance.
- `references/external-read-databases.md` — databases the service reads but
  doesn't own, and untrusted or LLM-authored SQL.
- `references/psycopg.md` — direct psycopg, `psycopg_pool`, LangGraph checkpointer.
- `references/alembic-migrations.md` — async `env.py`, run serialization,
  runner commands, writing revisions, migration tests, transaction semantics,
  backfills, one head, fresh-database replay, squashing, the rollout runbook.
- `references/schema-verification.md` — the database-contract CI job, parity
  tests, pinning `op.execute` objects, the runtime schema-revision guard,
  disposable test databases.
- `references/docker-entrypoint.md` — the runtime `ENTRYPOINT`/`CMD` for
  running migrations in each repo shape.

## Core conventions

- **Exactly one `SQLModel.metadata` for the schema, and exactly one Alembic
  history for it.** In a monorepo both live once: metadata in the shared
  models package, history in a dedicated migration-runner deployable. Two
  histories against one physical database is the failure this layout prevents.
- **No module-level engine.** Bootstrap calls `build_engine(...)` once with
  pool sizes from settings and registers `engine.dispose` on its exit stack;
  one-shot processes use `NullPool` and dispose in `finally`
  (`references/engine-and-session.md`).
- **Bootstrap constructs session and UoW factories**, never repositories.
  Repositories are built per transaction.
- **Repositories never commit, begin or roll back.** Exactly one owner (a
  store method or a unit of work) draws each transaction through the
  service's single transaction helper, which also translates driver failures
  (`references/engine-and-session.md`, "Transactions and the unit of work").
- **Only `db/` (and shared DB libraries) runs SQL.** Application, domain and
  ports never do. Where inside `db/` a query goes, and when it becomes a
  packaged `.sql` resource, is in `references/repositories-and-queries.md`.
- Queues claim with one `UPDATE … FOR UPDATE SKIP LOCKED … RETURNING`, fence
  every later write on lease and state, and never hold locks across external
  I/O (`references/work-queues.md`).
- Every autogenerated revision is read by a human before commit.
  Autogenerate detects structural drift only; it writes no backfills.
- A fresh database replays the **entire** history, so a migration that can
  fail closed blocks every fresh install unless that path is provided for, and
  never-deployed history is squashed to a verified baseline before the first
  deployment (`references/alembic-migrations.md`).
- "Migrations match models" is verified continuously: CI applies the real
  history to a scratch database and runs `alembic check`, and `op.execute`
  objects get their own pin (`references/schema-verification.md`).

## Related skills

- `python-repository-setup` — repo-shape decision, workspace mechanics,
  per-member `pyproject.toml`, Docker builds. Use it first for the monorepo
  case.
- `python-settings-config` — where the database URL, credentials and pool
  sizes are read from. `build_engine` takes resolved values; it doesn't
  source them.
- `python-service-architecture` — bootstrap, ports, errors
  (`../python-service-architecture/references/errors.md`), resource lifecycle
  (`../python-service-architecture/references/async-and-lifecycle.md`) and test
  placement (`../python-service-architecture/references/testing.md`).
- `python-code-conventions` — language-level idioms used by every example
  here (frozen kw-only dataclasses, closed vocabularies, no `assert`).
