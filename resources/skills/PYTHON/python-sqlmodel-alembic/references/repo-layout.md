# Repo Layout: Monorepo vs. Single-Service

The internal architecture is identical in both cases: models → `alembic/` →
`engine.py` → `transactions.py` → stores and named `db/` modules. What differs
is **which pieces are shared and which are per-service**.

## Single-service repo

Everything lives together under the one package's source tree:

```text
repo/
├── pyproject.toml
├── alembic.ini                          # script_location points below
└── src/
    └── myservice/
        └── db/
            ├── models.py             # naming convention, table base, tables;
            │                         # models/ (with base.py) when a table gains
            │                         # relationships or behaviour
            ├── engine.py             # build_engine, build_session_factory
            ├── transactions.py       # transaction helper, UoWs, constraint_name,
            │                         # transaction limits, database clock
            ├── users.py              # a store: implements one port
            ├── reports.py
            ├── alembic/
            │   ├── __init__.py       # package markers satisfy Ruff INP001;
            │   ├── env.py            # or add a per-file INP001 ignore
            │   └── versions/
            │       └── __init__.py
            └── queries/              # optional: long static SQL only
                └── monthly_report.sql
```

The engine itself is built in `bootstrap/`, not in `db/`
(`engine-and-session.md`).

## Monorepo (uv workspace)

The schema — `base.py` and `models/` — is the one thing every service must
agree on, so it lives **once**, in a shared workspace member with no
deployable of its own. The Alembic history that versions that schema is
itself a deployable — it's exactly the thing a migration-runner task/job
executes — so it gets its **own** service, depending on the shared models
package rather than living inside it. Nothing downstream should have to
install `alembic` and a DB driver just because it depends on the table
definitions. Everything from `engine.py` down is *how a given process talks
to the database*: pool sizes come from each service's settings, and each
service has repositories only for the tables it touches, so those stay
per-service by default.

Per-service is not a licence to copy. Transaction helpers, clock helpers,
limit setters and shared predicates follow the duplication and extraction
triggers in `../../python-service-architecture/references/shared-libraries.md`:
a module identical in ≥3 deployables, or two copies that have diverged
semantically, is extracted (to `db_models` or a shared DB library) or
commented with why the semantics differ. Code that differs in meaning,
lifecycle or dependencies stays local.

```text
repo/
├── pyproject.toml                        # workspace root
├── uv.lock
├── libs/                                 # or packages/ — match whatever
│   └── db_models/                        # this repo already uses
│       ├── pyproject.toml                # deps: sqlmodel, sqlalchemy — nothing heavier
│       └── src/
│           └── db_models/
│               ├── __init__.py
│               ├── base.py               # shared metadata + reusable table base
│               ├── vocabulary.py         # StrEnums; no SQLAlchemy import
│               └── models/
│                   ├── __init__.py
│                   ├── user.py
│                   └── report.py
│
└── services/
    ├── db-migrate/                       # the only thing that owns Alembic
    │   ├── pyproject.toml                # deps: db-models{workspace=true}, alembic, asyncpg
    │   ├── Dockerfile
    │   ├── alembic.ini
    │   ├── alembic/
    │   │   ├── env.py                    # imports db_models.base / db_models.models
    │   │   └── versions/
    │   └── src/
    │       └── db_migrate/
    │           └── __init__.py           # empty — this service has no app code
    │
    ├── api/
    │   ├── pyproject.toml                # depends on db-models (workspace=true)
    │   └── src/
    │       └── api/
    │           └── db/
    │               ├── engine.py
    │               ├── transactions.py
    │               └── users.py
    └── worker/
        ├── pyproject.toml
        └── src/
            └── worker/
                └── db/
                    ├── engine.py
                    ├── transactions.py
                    ├── reports.py
                    └── queries/          # optional
                        └── monthly_report.sql
```

`db_models` is a workspace member exactly like any shared library in the
`python-repository-setup` skill: its own `pyproject.toml`, no
`Dockerfile` of its own, consumed via `{ workspace = true }`. `db-models` is
just a placeholder name — call it whatever fits the domain (`db-schema`,
`core-db`, …); what matters is that it holds *only* schema and vocabulary
(`base.py`, models, SQLAlchemy-free enums, shared predicates and transition
builders), never runs queries or reads session state, and pulls in nothing
heavier than a service needs. `db-migrate` is a placeholder too — the point
is that it's a
`services/` member (it ships as its own image, per the deployable-unit rule
in `python-repository-setup`), not a `libs/` member.

Each app service's `pyproject.toml` declares:

```toml
[project]
dependencies = ["db-models", "sqlalchemy[asyncio]", "asyncpg"]

[tool.uv.sources]
db-models = { workspace = true }
```

`db-migrate`'s `pyproject.toml` declares the migration-specific dependencies
that no other service needs:

```toml
[project]
dependencies = ["db-models", "alembic", "asyncpg"]

[tool.uv.sources]
db-models = { workspace = true }
```

### Why migrations are never split per service

`users`/`reports`/whatever the actual tables are live in **one physical
database**. If each service kept its own Alembic history against that same
database, two services could each believe they own the "next" revision, race
on `alembic_version`, or — worse — one service's migration silently drops a
column another service still reads. Concentrating the Alembic history in one
dedicated migration-runner service, importing the one shared models package,
makes this structurally impossible: there is exactly one place that can
generate a revision, because there's exactly one place with both `alembic`
installed and the model metadata to diff against. See
`references/alembic-migrations.md` for how that one history runs in
practice — still just `alembic upgrade head`, run as this service's
container command.

## Schema ownership and prototype mode

- Every schema object has one owning deployable and one versioned history.
  Disjoint owners in one database get separate version tables (Alembic
  `version_table_schema`, or the library's own for a library that migrates
  its tables, such as a LangGraph checkpointer). Cross-owner dependencies (a view over another
  owner's tables) are declared, and the deploy graph enforces their order.
- `create_all()` and hand-rolled initializers are allowed only in a declared
  **rebuild-only prototype mode**, stated in the module docstring. It ends at
  the first persistent environment or the second DDL owner, whichever comes
  first. One-shot initializers take an advisory lock.
- A consumer's column contract over a shared schema is derived from the
  shared metadata, not re-typed. Contract tests compare column **types**, not
  only names.
