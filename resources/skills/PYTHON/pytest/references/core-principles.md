# Core production-testing principles

Use these rules for every pytest task, regardless of framework.

The entrypoint defines risk selection, proof profiles, and the quality gate.
This reference covers the mechanics that keep otherwise valuable tests honest,
isolated, and maintainable. Load the framework or integration reference for
boundary-specific behavior rather than generalizing from a test double.

## Use doubles deliberately

Choose the least magical double that expresses the contract:

- **Stub:** returns a controlled outcome.
- **Fake:** small working implementation, useful for stateful port behavior.
- **Spy or recorder:** captures meaningful interactions for later assertions.
- **Mock:** encodes interaction expectations; reserve it for interaction
  contracts or awkward third-party boundaries.

Prefer an explicit typed fake at an application port. It makes setup readable,
supports state assertions, and survives harmless call rearrangement. A concrete
adapter unit test may replace its direct HTTP, SDK, model, clock, or filesystem
collaborator because that adapter is the subject.

### Doubles must be correct

A wrong double makes every test that uses it pass for the wrong reason.

- **Unit-of-work fakes are transactional.** Writes become visible only on
  `commit()`, and leaving the unit of work without a commit discards them.
  Assert on the committed store; counting commits is not a substitute.
- **Doubles record; tests assert.** Never put `assert` inside a double: when
  production code calls it under `except Exception`, the failure is swallowed
  and the test passes vacuously. To reject an unexpected call, raise a
  test-support `UnexpectedCall(BaseException)`, which escapes those handlers.
- Record what the double received, in order, without sorting, deduplicating,
  or canonicalizing.
- **Scripted models, tools, and runners fail when exhausted.** Raise
  `AssertionError("unscripted call N to <name>")`; never repeat the last
  response. Switch to `UnexpectedCall` when a production `except Exception`
  sits between the double and the test and the framework in between propagates
  `BaseException` (LangChain's async chat-model path does not).
- Every harness or builder parameter is used; delete unused helpers.
- Prefer a small typed recording fake (`fake.decisions == [...]`) over
  `call_args`/`await_args` archaeology.
- Default to zero `unittest.mock`. Use `httpx.MockTransport` for HTTP and
  `create_autospec(Port, instance=True)` rather than `patch` when a generated
  double is needed. Never use a spec-less `Mock` or `AsyncMock` for a port.
- Keep one fake per port per member. When a fake, builder, or harness moves
  into the support package is owned by `$python-service-architecture`
  ([testing.md](../../python-service-architecture/references/testing.md#test-support-packages)).
- Doubles type-check against the port `Protocol`: test support is in the mypy
  run, and a fake that is never passed where the port is expected gets an
  explicit check such as `_: OrderRepository = InMemoryOrders()`.

When patching is necessary:

- patch the name where the code under test looks it up, not where the object was
  originally defined;
- use `autospec=True` or `spec_set` so the double cannot accept a nonexistent
  API;
- let missing attributes and environment keys fail instead of silently creating
  them;
- scope and restore every patch through a context manager, fixture, or
  `monkeypatch`.

Avoid mocks of the subject, private helpers, SQLAlchemy internals, FastAPI
internals, Celery delivery machinery, or LangGraph runtime internals. Do not
assert calls that merely restate the implementation unless call count, order,
or arguments carry business or protocol meaning.

### Stop at a missing seam

Stop and propose a production seam, instead of adding more patches, when a test:

- needs more than three `monkeypatch.setattr` calls on one module, or patches
  in more than one module;
- patches `_private` names, instrument globals, `trace.get_tracer`, or
  `asyncio`/`httpx` attributes;
- raises an exception to abort production code midway;
- needs `SimpleNamespace` to stand in for a typed runtime.

Seam shapes to propose: settings-to-policy as a pure function; a composition
root that accepts constructed resources or builder callables; one iteration as
a plain worker function; caches observed through factory-call counts; an adapter that takes a
connection factory instead of calling `connect()` itself.

Patching public module-level factories in one module is tolerated when
production changes are not authorized. One in-process wiring smoke test per
service may keep a few patches.

## Fixtures reveal ownership and cost

Use fixtures for lifecycle and reusable setup, not to conceal the scenario.
Setup that carries no scenario facts should become a fixture once it repeats.

- Default to function scope and fresh mutable state.
- Which `conftest.py` a fixture lives in (narrowest common ancestor; expensive
  infrastructure under the profile that needs it, never root) is owned by
  `$python-service-architecture`
  ([testing.md](../../python-service-architecture/references/testing.md#fixtures-and-static-data)).
- Prefer explicit fixture parameters over distant `autouse` behavior. A narrow
  autouse safety guard, such as blocking the public network in unit tests, is a
  justified exception.
- Heuristic: each fixture owns one cohesive setup concern and pairs it with its
  teardown. Composing small yield fixtures keeps cleanup safe when later setup
  fails.
- Use `yield` for lifecycle resources and restore pre-existing global state in a
  `finally` path.
- Broaden resource startup scope only when per-test mutable state is still
  isolated by unique database/schema, transaction, queue, namespace, tenant,
  directory, or identifier.
- Resolve paths from `__file__` and read environment variables inside
  fixtures, never at import time (testing.md, as above). Test bodies never read
  `os.environ` directly.

Reusable doubles, builders, and harness types are importable support code, not
fixtures. Never write:

- a fixture returning a module (`sys.modules[__name__]`);
- a fixture returning a class or function just so tests can reach it;
- `type(fixture().attr)` to recover a type;
- an import of another deployable's test helpers.

Use a plain local value or builder when the facts are important to reading the
test. Deep fixture graphs that manufacture the entire application make it hard
to see causality and often create accidental shared state.

### Typed fixtures and builders

- Fixtures and builders return concrete types, never `Any`. Replace a tuple
  fixture with a frozen dataclass.
- Give each important domain type a keyword builder (`owned_work(...)` with
  defaults) that goes through the real constructor. Vary it with
  `dataclasses.replace` or `model_copy(update=...)`; never
  `Model(**values)  # type: ignore`.
- Seed integration data through typed row builders, not inline `INSERT` SQL,
  unless the SQL is under test.
- Application tests do not construct `Settings`; they receive the policy
  values or collaborators built from it.

### Parametrization

Parametrize true equivalence classes or boundary values that share one action
and oracle. Every non-trivial case is a `pytest.param(..., id=...)`, every
parameter is used, and the body never branches on a parameter: split success
and failure tables. Split cases whose setup, expected behavior, or failure
explanation differs materially.

Pytest passes parameter objects as-is rather than copying them. Never mutate a
shared mutable parameter across cases; build a fresh object inside the test or
through a factory.

## Oracles

- A structured log event name plus its meaningful fields is a valid oracle when
  the event is an operational contract. Capture it with the logging library's
  helper, such as `structlog.testing.capture_logs`, and use one capture
  mechanism per suite. Never match prose (`"... failed" in caplog.text`).
- Redaction is proved with canaries: feed a unique secret-shaped value through
  the path and assert it is absent from every captured output.
- Contract tests over compose files, deployment manifests, or configuration
  assert structural facts from the parsed document, not substrings of shell
  commands. A SQL-text assertion in a unit test is acceptable only when an
  integration test proves the effect.
- Prompt tests keep one reviewed snapshot per prompt, paired with its version
  constant; other prompt tests check invariants with whitespace-normalized
  matching.

## Make time, randomness, and concurrency observable

- Inject clocks, sleep/backoff functions, ID generators, and random sources into
  application logic where the architecture already permits it.
- Freeze wall time only when injection is impractical. Remember that a frozen
  test-process clock does not advance a broker, worker container, database, or
  provider clock.
- Unit tests never sleep in real time. Drive timeouts with an injected clock;
  never `sleep(2 * timeout)`.
- Wrap every `await` on an event, queue, task, or future in
  `asyncio.timeout(...)`, at most 1 s in unit tests. Poll only through one
  bounded helper (`await wait_until(predicate, within_seconds=1)`); never write
  `while cond: await asyncio.sleep(0)` or count event-loop yields.
- For "nothing happens" assertions, drive a deterministic step (manual clock
  plus one worker-function call). When a real broker makes that impossible, name the window as
  a constant and keep the test in the integration profile.
- Test builders default to minimal time budgets (at most 0.1 s). A unit test
  slower than about 1 s is a defect; check `--durations`.
- Never coordinate concurrency with `sleep()`. Use events, barriers, task
  groups, channels, or database locks. Prove order independence by forcing an
  adversarial completion order, such as releasing per-item events in reverse,
  not with random sleeps.
- Force the intended interleaving explicitly, then assert from the main test
  thread or task. Join every spawned thread and finish or cancel every task in
  fixture teardown.
- Avoid order dependence and uncontrolled global state even in a serial suite.
  When parallel execution is used or planned, give each worker unique ports,
  queues, broker namespaces, database schemas, paths, IDs, and graph thread IDs.
  Identify real-infrastructure resources with `uuid4()`, not timestamps.
- Seed ordinary randomness when it is part of a deterministic example. For
  property-based testing, preserve and replay the framework's minimized
  failures rather than replacing exploration with a few random loops.

A rerun plugin may collect evidence, but it is not a repair for a flaky test.
Quarantine only with an owner, narrow condition, deadline or issue, and visible
reporting.

## Async tests

Runtime rules for the code under test (task ownership, cancellation, timeouts,
shutdown) are owned by `$python-service-architecture`:
`../../python-service-architecture/references/async-and-lifecycle.md`.

- Write native `async def` tests with the plugin the repository already has,
  AnyIO or pytest-asyncio. If neither is installed, adding one is a dependency
  change: propose it rather than working around it.
- Never wrap a test body in a nested `async def run()` plus `asyncio.run(run())`.
  `asyncio.run` belongs only in a process-level end-to-end test of `main()`.
- Mark async modules once with a module-level `pytestmark`
  (`pytest.mark.anyio`, or `pytest.mark.asyncio(loop_scope=...)`), not per
  test. When both plugins are installed, avoid conflicting auto modes.
- AnyIO's default test backend behavior may exercise more than asyncio. If the
  application intentionally supports only asyncio, configure that explicitly
  (an `anyio_backend` fixture returning `"asyncio"`). If multiple backends are
  supported, treat the matrix as a deliberate contract.
- Create loop-bound clients, pools, sessions, and checkpointers inside the loop
  and lifecycle in which they run, never at module import time.
- Align async fixture lifetime with event-loop lifetime. With pytest-asyncio, a
  shared engine is `@pytest_asyncio.fixture(scope="session",
  loop_scope="session")` and the tests using it run with
  `pytest.mark.asyncio(loop_scope="session")`. With AnyIO, a higher-scoped
  async fixture needs an `anyio_backend` fixture of the same scope.
- Do not share one `AsyncSession` across concurrent tasks.
- Test cancellation and cleanup when the production code promises them; do not
  merely cancel and ignore leaked work.

Framework plugin APIs and loop-scope defaults change. Honor locked versions and
current repository configuration rather than adding a global `event_loop`
fixture copied from an old example.

## Framework characterization

Third-party behavior the application depends on (a reducer's merge rule, a
serializer's null handling, a router's precedence) belongs in a framework
characterization profile, not scattered through unit tests:

- name each test after the assumption it protects
  (`test_add_messages_reducer_replaces_message_with_same_id`);
- run a minimal synthetic graph, model, or schema, not application code;
- include one test that pins the locked versions of the characterized
  packages;
- rerun the profile on every dependency bump; a failure is a review trigger,
  not something to patch around.

Unit tests then do not re-assert framework shape.

## Suite hygiene

- When behavior is removed or renamed, update every profile (unit,
  integration, E2E, live) in the same change; the `--collect-only` job that
  enforces it is owned by
  [testing.md](../../python-service-architecture/references/testing.md#profiles-and-markers)
  ("CI selection").
- Delete per-module `pytest.skip` fallbacks; every infrastructure prerequisite
  goes through the one `require_env` helper in the support package, which skips
  locally and fails when `REQUIRE_INTEGRATION=1`
  ([examples-core.md](examples-core.md#profile-prerequisites-skip-locally-fail-when-required)).
- Delete spike and prototype code from the collected suite once the decision is
  recorded. Keep scripts with a `main()` outside `tests/`.
- Prove that importing a module is inert (no connections, threads, or
  environment reads) in a subprocess, not in the already-warmed test process.

## Live checks

A live test calls a shared or paid external provider. Its placement and CI job
are owned by
[testing.md](../../python-service-architecture/references/testing.md#profiles-and-markers);
the test design:

- A live test module sets `pytestmark = pytest.mark.live` and is excluded from
  the default suite. Run it in an explicit scheduled, pre-release, or
  provider-compatibility job.
- It fails rather than skips when its required environment is missing.
- Inject secrets through the approved CI mechanism, and bound calls, tokens,
  concurrency, time, latency, cost, and data.
- Assert types, schema, bounded shapes, and termination, not exact provider
  output or natural-language wording.
- A cassette improves repeatability but proves the recorded response, not the
  provider's current behavior. Redact it, version it when schemas change, and
  retain a tiny uncached smoke when live compatibility matters.

## Property-based and stateful testing

Use Hypothesis when invariants cover an input or operation space better than a
handwritten example:

- parse/serialize and encode/decode round trips;
- normalization idempotence;
- balances, quotas, conservation, and ordering properties;
- schemas with missing, extra, malformed, and boundary values;
- duplicate delivery and retry classification;
- state-machine transitions, deduplication, and outbox sequences.

Keep properties deterministic and give each generated example isolated mutable
state. Compare complex systems with a deliberately simple reference model. Add
important discovered failures as explicit `@example` or named regressions so
they remain part of the permanent contract. Do not suppress health checks,
deadlines, or flaky failures without understanding their cause.

Property-based testing complements named examples; it does not replace a clear
business oracle.

## Coverage, mutation, and test sensitivity

Use line and branch coverage to locate important code with no executed scenario
and to notice that a test command did not run what was expected. Never infer
test quality from the percentage: a test can execute every line and assert the
wrong thing.

If the repository enforces a threshold, preserve it unless asked to change it,
but do not weaken assertions or add valueless tests to satisfy it. Explain
whether uncovered code represents risk, defensive impossibility, generated
code, or a different test profile.

For compact high-risk deterministic logic, targeted mutation testing can reveal
tests that execute code without detecting behavioral changes. Use it as a
diagnostic when the project already supports it or adding it is in scope; review
surviving mutations semantically rather than chasing a mutation score.

## Primary references

- [pytest good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [pytest fixtures and safe teardown](https://docs.pytest.org/en/stable/how-to/fixtures.html#safe-teardowns)
- [pytest parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [pytest monkeypatch guidance](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
- [pytest assertions and expected exceptions](https://docs.pytest.org/en/stable/how-to/assert.html)
- [pytest flaky-test guidance](https://docs.pytest.org/en/stable/explanation/flaky.html)
- [Python mock patching and autospeccing](https://docs.python.org/3/library/unittest.mock.html#where-to-patch)
- [Hypothesis introduction and useful properties](https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html)
- [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html)
- [coverage.py branch coverage](https://coverage.readthedocs.io/en/latest/branch.html)
- [pytest's example of a bug despite full coverage](https://docs.pytest.org/en/stable/explanation/types.html)
- [Test Coverage as a diagnostic, not a quality number](https://martinfowler.com/bliki/TestCoverage.html)
