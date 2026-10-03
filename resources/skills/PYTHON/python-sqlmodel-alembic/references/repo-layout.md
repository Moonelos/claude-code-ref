# Repo Layout: Monorepo vs. Single-Service

The internal architecture is identical in both cases: models → `alembic/` →
`engine.py` → `transactions.py` → one store per contract, laid out as in
[The db/ package](#the-db-package). What differs is **which pieces are shared
and which are per-service**.

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
            ├── users.py              # SqlUserStore: implements ports/users.py
            ├── reports.py            # SqlReportStore: implements ports/reports.py
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

## The db/ package

Every service's `db/` has the same shape, in either repo layout. Its root holds
two kinds of entries: **shared** modules that capabilities use, and one entry
per **capability**, each the implementation of one contract.

```text
db/
├── models.py | models/         # shared: the schema (single-service repo)
├── tables.py                   # shared: handles over a shared schema library
├── engine.py                   # shared: build_engine, build_session_factory
├── transactions.py             # shared: transaction helper, UoWs, limits, clock
├── repositories.py             # shared: a repository several stores use
├── readiness.py                # shared: the database readiness probe
├── schema.py                   # shared: runtime schema-revision guard
├── retention.py                # shared: technical jobs no port fronts
├── <responsibility>.py         # shared: a helper several capabilities use
├── alembic/                    # shared: migrations (single-service repo)
├── queries/                    # shared: long static SQL only
├── <capability>.py             # stage 1: Sql<Capability>Store
└── <capability>/               # stage 2
    ├── __init__.py             # empty
    ├── store.py                # Sql<Capability>Store and its repositories
    └── <responsibility>.py     # supporting modules, named by what they do
```

Create a shared module only when something needs it. Table handles live in one
place: `models.py` when the service owns the schema, `tables.py` when it reads
a shared schema library (`USERS = metadata.tables["app.users"]`). A helper
outside the standard names above is shared only while several capabilities
import it, is named by its responsibility (`fencing.py`), and is never wired
in bootstrap. Every other root entry is a capability, and these rules fix its
place and name:

1. **The name follows the contract.** `ports/orders.py` declares `OrderStore`,
   so `db/orders.py` defines `SqlOrderStore`. When one port module declares
   several stores, each takes its Protocol's name (`StatusStore` →
   `db/status.py`, `WorkQueue` → `db/queue.py`). An implementation of a
   consumer-private Protocol takes its consumer's name
   (`genai/retrieval/` → `db/retrieval.py`). A second implementation of the
   same port takes a suffix (`db/orders_legacy.py`). *Why:* a reader or agent
   finds the implementation from the port without searching, and every service
   lands on the same file names.
2. **Start flat.** One module per capability. Its repositories, row mapping,
   and helpers no other capability uses are in that module. *Why:* most stores
   fit one file, and a package around one file only adds navigation.
3. **Promote to `db/<capability>/` when the implementation gains supporting
   modules only it uses**, such as row mapping, query builders, or
   lease/publication steps, and one file is no longer easy to read. The move is
   mechanical: `db/orders.py` becomes `db/orders/store.py` with the same class
   name, callers import from `store` directly, and `__init__.py` re-exports
   nothing. When method groups serve different actions, split the port instead
   (`../../python-service-architecture/references/boundaries.md#application-ports`).
   *Why:* growth is one predictable move, not a redesign, and there is no
   facade to keep in sync.
4. **Capabilities never import each other.** Anything two capabilities need
   (table handles, predicates, the transaction helper, a shared repository)
   moves to a shared root module. *Why:* each capability changes and is tested
   alone, and one store's internals never become another's API.
5. **Grouping adds no layer.** A capability subpackage holds no coordinator,
   facade, or per-table repository created to fill it. *Why:* the folder exists
   for navigation, not indirection.

A service without `ports/` (a migration runner) has no capabilities; its `db/`
holds only shared modules.

`python-service-architecture-audit` flags a capability whose name matches no
port module or Protocol, a subpackage without `store.py` or with one module, a
shared helper only one capability imports, and imports between capabilities.

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
