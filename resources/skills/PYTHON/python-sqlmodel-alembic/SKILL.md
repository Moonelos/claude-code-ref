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
models.py           naming convention, table base, SQLModel tables, column vocabularies
   ↑                (a models/ package with base.py once tables gain relationships)
alembic/            the one migration history for that metadata
   ↑
engine.py        →  transactions.py          →  one store per port (db/<port>.py)
engine builder +    transaction helper, UoWs,    entity reads/writes; leases,
session factory     constraint_name, limits,     retention, external reads
(bootstrap calls)   database clock               (optional: queries/*.sql)
```

`models.py` describes the schema; `alembic/` versions it. `engine.py` and
`transactions.py` are how one process talks to that schema. Every `db/` follows
one template (`references/repo-layout.md`, "The db/ package"): a closed set of
shared root modules, then one store per contract named after its port
(`db/orders.py`), promoted to `db/orders/store.py` only when it gains
supporting modules. No module for one helper: the session factory lives with
the engine builder, and the clock, limits, and integrity helpers live with the
transaction helper.

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

- `references/repo-layout.md` — the `db/` package template, monorepo vs.
  single-service trees, what is shared vs. per-service, schema ownership and
  prototype mode.
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
  history for it** (`references/repo-layout.md`, "Why migrations are never
  split per service").
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
- Pin `sqlalchemy[asyncio]` to the range the locked `sqlmodel` supports
  (`sqlmodel` 0.0.x requires SQLAlchemy `<2.1`); upgrade them together.
- Every autogenerated revision is read by a human before commit
  (`references/alembic-migrations.md`, "Day-to-day workflow"); data work is
  hand-written ("Data backfills are written, never generated").
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
- `python-settings-config` — where the database DSN (a secret), pool sizes
  and the migration process's own secrets model are read from. `build_engine`
  takes resolved values; it doesn't source them.
- `python-service-architecture` — bootstrap, ports, errors
  (`../python-service-architecture/references/errors.md`), resource lifecycle
  (`../python-service-architecture/references/async-and-lifecycle.md`) and test
  placement (`../python-service-architecture/references/testing.md`).
- `python-code-conventions` — language-level idioms used by every example
  here (frozen kw-only dataclasses, closed vocabularies, no `assert`).
