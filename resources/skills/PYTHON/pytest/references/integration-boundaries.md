# Framework-neutral integration boundaries

Use this reference for a Python backend that reaches databases, filesystems,
processes, or remote services without a more specific FastAPI, worker, or
LangGraph reference, and for cross-cutting suite selection or CI design.

## Keep profiles complementary

Use cheap deterministic tests where behavior can be isolated, real integration
tests for production boundaries whose semantics the application relies on, and
a small number of broad tests for wiring and critical journeys. This is a risk
portfolio, not a required ratio.

- Push exhaustive decision tables down to pure or application tests.
- Test adapter request construction and error translation with a transport or
  SDK fake, then use a smaller real-infrastructure test for encoding, lifecycle,
  configuration wiring, and compatibility.
- Keep E2E scenarios outcome-focused. If an E2E failure exposes a branch not
  covered below, add the narrow regression and retain the E2E case only when it
  still proves distinct wiring.
- Do not call a test unit merely because it uses mocks or integration merely
  because it imports a framework. Classify executed dependencies.

## Databases

This section owns database-test rules for every framework; the FastAPI and
worker references link here.

### Match production semantics

- Use an explicitly test-scoped disposable database. The guard that makes
  destructive setup refuse ordinary service URLs (a separate
  `INTEGRATION_<DB>_DATABASE_URL`, a `test_` database name) is owned by
  `$python-sqlmodel-alembic`
  ([schema-verification.md](../../python-sqlmodel-alembic/references/schema-verification.md#disposable-test-databases)),
  as are the claim, lease, and fencing rules that work-queue tests exercise
  ([work-queues.md](../../python-sqlmodel-alembic/references/work-queues.md#work-claiming-and-leases)).
- Keep one engine fixture per member. Prefer a unique schema or tenant
  namespace per test over table wipes; any wipe first asserts that it targets a
  test database.
- Test repositories, constraints, migrations, transaction isolation, locking,
  concurrency, and dialect-specific SQL on the production database family.
- Migrations in CI (real history applied to an empty database, `alembic check`,
  heads, downgrade policy, the migration-test fixture and runner helper) are
  owned by `$python-sqlmodel-alembic`
  ([schema-verification.md](../../python-sqlmodel-alembic/references/schema-verification.md#the-standing-harness-a-database-contract-ci-job)).
- Use one SQLAlchemy `Session` per thread and one `AsyncSession` per async task.

SQLite is valid evidence when production is SQLite or the test deliberately
proves dialect-independent application behavior. It is not a PostgreSQL or
MySQL compatibility layer and not evidence for PostgreSQL transactions,
constraints, locking, types, or migrations.

### Transaction isolation fixture

For same-connection SQLAlchemy tests, the SQLAlchemy 2.x external-transaction
recipe can bind a session with `join_transaction_mode="create_savepoint"` to a
connection inside an outer transaction
([example](examples-core.md#sqlalchemy-same-connection-transaction-fixture)).
Application code may commit or roll back its session, while teardown rolls back
the outer transaction. It makes same-connection tests fast, but it is not a
universal isolation mechanism:

- another connection, process, or worker cannot see uncommitted fixture data;
- commits made on another connection are outside the outer rollback;
- rollback-only tests can hide commit visibility, locking, and race defects;
- sharing a session across threads or an `AsyncSession` across tasks is unsafe.

Use committed setup plus a unique database, schema, or tenant, or an explicit
reset, for multi-connection, worker, outbox, and concurrency tests. Stop
dependent workers before cleanup. Re-read final state through a fresh session
when identity-map caching could satisfy the assertion.

### Minimum database confidence

Cover only the semantics the application relies on:

- mapped types and serialization;
- unique, foreign-key, check, and exclusion constraints;
- representative queries, ordering, pagination, and null behavior;
- commit, rollback, and no partial state after failure;
- optimistic or pessimistic locking and important race outcomes;
- idempotency/deduplication under separate concurrent connections;
- migration from blank to head and from each operationally supported prior
  release snapshot (harness: the migrations bullet above);
- application transaction plus outbox/enqueue timing.

## HTTP and external services

At an owned adapter boundary, cover only the request and response behavior the
application relies on:

- method, URL, selected headers, auth, timeout, encoding, and correlation or
  idempotency key;
- schema-tolerant parsing and application-owned error translation;
- retry classification for timeout, cancellation, selected 4xx/5xx responses,
  and malformed payloads;
- absence of accidental public network in the default suite.

A transport fake or disposable local protocol endpoint is usually more stable
than patching client-library internals. Add an opt-in provider contract or live
smoke only for compatibility a local substitute cannot prove; how live checks
are bounded, selected, and asserted, and what a cassette proves, is in
[core-principles.md](core-principles.md#live-checks).

For independently deployed services, consumer-driven contracts can complement
provider integration. Include only fields the consumer depends on and verify the
contract against the provider; do not turn a full payload snapshot into a false
compatibility guarantee.

## Filesystems, subprocesses, and CLIs

- Use `tmp_path` or another isolated disposable root and assert externally
  observable files, permissions, exit codes, stdout/stderr contracts, and
  cleanup.
- Do not patch file I/O when atomic rename, locking, path encoding, permissions,
  or crash recovery is the behavior under test.
- Bound subprocess execution, capture output, and terminate descendants during
  teardown. Avoid relying on the developer's current working directory, shell
  aliases, or global environment.
- Contract-test installed entry points and package resources through the same
  installation shape used in CI or deployment.

## Skips, xfails, warnings, and CI jobs

These are review and design criteria. Do not modify pytest configuration or CI
unless the user's requested scope includes those files; otherwise report the
specific change required.

- `skip` means the test cannot apply in the selected environment. `xfail` is
  only for a precise known defect or dependency limitation, under the rule in
  the [quality gate](../SKILL.md#quality-gate).
- Assert intentional warnings with `pytest.warns`. Do not hide project or
  dependency deprecations behind broad filters.
- Profile selection, the fail-when-absent rule, and one direct command per
  profile are owned by `$python-service-architecture`
  ([testing.md](../../python-service-architecture/references/testing.md#profiles-and-markers),
  "CI selection"). Preserve counts and useful artifacts such as service logs,
  request/correlation IDs, and minimized Hypothesis examples.
- Favor deterministic tests and proportionate disposable integration in PR
  feedback. Put destructive recovery, broad process topology, long property
  profiles, and live-provider checks in explicit jobs.

Do not require parallel CI for a serial project. Tests should still avoid order
dependence and uncontrolled global state; add xdist-specific resource isolation
when parallel execution is used or planned.

## Primary references

- [pytest good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [pytest skips and expected failures](https://docs.pytest.org/en/stable/how-to/skipping.html)
- [pytest temporary paths](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [SQLAlchemy external-transaction recipe](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [SQLAlchemy session concurrency](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks)
- [SQLAlchemy SQLite transaction differences](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver)
- [Testcontainers for Python with PostgreSQL](https://testcontainers.com/guides/getting-started-with-testcontainers-for-python/)
- [Pact contracts](https://docs.pact.io/getting_started/how_pact_works)
