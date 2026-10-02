# FastAPI and backend boundaries

Use this reference for FastAPI, Starlette, ASGI lifecycle, async API tests, and
database-backed request paths. Inspect the installed FastAPI, Starlette, client,
AnyIO or pytest-asyncio, SQLAlchemy, and Alembic versions before adapting an
example; these APIs and defaults evolve together.

## Split the proof by responsibility

Do not make every behavior an HTTP test. Use complementary boundaries:

| Responsibility | Faithful test |
| --- | --- |
| Domain and application decisions | Call the action directly with explicit fakes |
| Request parsing, dependency wiring, auth policy, status, response schema, exception mapping | In-process ASGI request with outer effects replaced |
| App construction, startup failure, shared resource creation and disposal | App-factory/lifespan test |
| Repository queries, constraints, transactions, migrations | Production-dialect disposable database integration |
| HTTP plus database transaction/outbox behavior | API integration with a bound real session/database |
| Reverse proxy, deployed middleware, process configuration, multiple real boundaries | Small E2E or deployed smoke suite |

Keep exhaustive business branch tables below the HTTP layer. API tests prove
transport-owned behavior and a few representative vertical flows.

## Construct an isolated application

- Prefer an application factory that accepts settings or a runtime/composition
  object. Tests should create an app with explicit test configuration rather
  than importing a module-global app that connected to services at import time.
- Put loop-bound pools, clients, models, and workers in lifespan. Importing a
  router or pure application action must not require credentials or open a
  connection.
- Use one app per test when its state or overrides mutate. A wider app fixture is
  acceptable only when all per-test mutation is restored and lifecycle
  semantics are intentional.
- Test startup validation and cleanup separately from route behavior. Force
  resource-construction failure and verify later resources are not leaked.

### Dependency overrides

FastAPI overrides are keyed by the exact original dependency callable and
replace its subdependency tree. They are global mutable application state.

- Override an owned outer dependency, such as an application action, current
  principal, or session provider. Do not patch FastAPI's dependency resolver.
- Keep a separate test for the real dependency. A route suite with fake auth or
  database access does not prove those integrations.
- Install overrides before entering lifespan if startup uses them.
- Restore the exact previous mapping in `finally`, even if app startup or the
  test fails. Clearing the dictionary can destroy unrelated pre-existing
  overrides in shared setups.
- Do not use one enormous dependency override that bypasses application-owned
  authorization, validation, and transaction behavior being tested.

## Synchronous request tests

Use a normal `def` test and `TestClient` when the test does not need to await
resources on the test's event loop.

- Enter `TestClient(app)` as a context manager whenever lifespan matters. Plain
  construction does not prove startup and shutdown behavior.
- Keep `raise_server_exceptions=True` by default so unexpected application bugs
  fail at their origin. Set it to false only in the focused test of the rendered
  500 response or error middleware.
- Test through public paths and real request serialization. Calling route
  functions directly bypasses validation, dependencies, middleware, exception
  mapping, and response-model filtering.
- Context-manage WebSocket sessions and assert closure or protocol errors as
  well as messages.

Starlette's synchronous client runs the ASGI app in its own thread/event loop.
Do not use it when the test must also await or inspect an async database client,
pool, lock, or other loop-bound object created by the test.

## Asynchronous request tests

Make the whole test async when it needs app-adjacent async resources.

- Follow the repository's async plugin, marker, and loop-scope setup
  ([core-principles.md](core-principles.md#async-tests)).
- Use the compatible ASGI transport/client for the installed FastAPI and
  Starlette versions and give the client a test base URL.
- HTTPX `ASGITransport` does not start lifespan. Wrap the app in a compatible
  lifespan manager and pass its state-aware app to the transport when lifespan
  state is used.
- Create the app's async clients and pools inside lifespan or async fixtures on
  the same loop that serves requests.
- Bound every async wait and clean up spawned tasks before fixture teardown.

## High-value HTTP behaviors

Select cases owned by the transport or visible at the service boundary:

- required, omitted, malformed, and meaningful boundary inputs;
- authentication versus authorization and tenant/resource isolation;
- not found, conflict, precondition, rate-limit, and idempotency semantics;
- application error to stable status/body/header mapping;
- response-model filtering so private fields do not leak;
- media type, cookies, caching, pagination, location, retry, and correlation
  headers when clients rely on them;
- transaction outcome and durable side effects, including outbox or scheduled
  work after the response;
- cancellation, timeout, disconnect, and cleanup when the API promises behavior
  for them;
- OpenAPI or schema compatibility only for the externally consumed subset.

Do not retest every Pydantic rule or FastAPI default. One representative 422
request can prove the boundary wiring; test application-owned validation and
error shape where it differs from framework defaults.

Avoid full response snapshots unless the entire document is a versioned public
contract. Prefer semantic JSON assertions and separate schema/contract tests for
large documents.

## Background tasks and work submission

An in-process API test can prove that the endpoint schedules or publishes the
right work after the right preconditions. It cannot prove a separate worker
discovers, deserializes, retries, or acknowledges that work.

- Test the background callable or application action directly for its branch
  matrix.
- At the HTTP boundary, assert the accepted response and the stable task/event
  envelope or outbox record.
- Verify publication timing relative to commit and rollback. A worker must not
  race an uncommitted row.
- Add worker/broker integration in the worker suite for delivery semantics.

For Starlette/FastAPI in-process background tasks, use a focused test only when
that mechanism is the production mechanism. Do not mistake same-process
completion under a test client for durable queue behavior.

## Streaming and WebSockets

Test the protocol consumed by the client, not incidental chunk boundaries.

- Assert status, media type, stable event/message schema, ordering guarantees,
  terminal signal, and error representation.
- Reconstruct semantic content across chunks. Network, model, and framework
  buffering can change chunk sizes without changing behavior.
- Test disconnect/cancellation and prove generators, sessions, locks, and other
  lifespan resources are released.
- For dependencies that `yield`, assert the intended cleanup point relative to
  stream completion. FastAPI's dependency-scope and streaming cleanup semantics
  have changed across releases, so lock versions and test the behavior relied
  on by the service.
- For WebSockets, cover handshake/auth rejection, message schema, normal close,
  and abnormal disconnect only when the application owns those policies.

## Database-backed tests

Database rules (production dialect, the disposable-target guard, the
same-connection transaction fixture and its limits, minimum database
confidence) are framework-neutral and owned by
[integration-boundaries.md](integration-boundaries.md#databases); migrations in
CI are owned by `$python-sqlmodel-alembic`
([schema-verification.md](../../python-sqlmodel-alembic/references/schema-verification.md#the-standing-harness-a-database-contract-ci-job)).
Through FastAPI, inject the test session or UoW factory through the owned
session-provider dependency, and verify through a separate fresh session
([example](examples-fastapi.md#async-client-with-explicit-lifespan)).

## Primary references

- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [FastAPI dependency overrides](https://fastapi.tiangolo.com/advanced/testing-dependencies/)
- [FastAPI lifespan testing](https://fastapi.tiangolo.com/advanced/testing-events/)
- [FastAPI async tests](https://fastapi.tiangolo.com/advanced/async-tests/)
- [FastAPI yield-dependency scope](https://fastapi.tiangolo.com/advanced/advanced-dependencies/#dependencies-with-yield-and-scope)
- [Starlette TestClient](https://www.starlette.io/testclient/)
- [HTTPX ASGI transport and lifespan note](https://www.python-httpx.org/advanced/transports/#asgi-transport)
- [ASGI lifespan specification](https://asgi.readthedocs.io/en/latest/specs/lifespan.html)
- [AnyIO pytest plugin](https://anyio.readthedocs.io/en/stable/testing.html)
- [pytest-asyncio configuration](https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html)
- [SQLAlchemy external-transaction test recipe](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [SQLAlchemy asyncio concurrency](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks)
- [SQLAlchemy SQLite transaction differences](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver)
- [Alembic autogenerate and `alembic check`](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#running-alembic-check-to-test-for-new-upgrade-operations)
- [Alembic head validation](https://alembic.sqlalchemy.org/en/latest/cookbook.html#test-current-database-revision-is-at-head-s)
