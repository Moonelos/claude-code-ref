---
name: pytest
description: >-
  Design, write, refactor, or review high-value pytest suites for production
  Python backends, especially FastAPI APIs, async code, workers and task
  queues, databases and external integrations, and LangChain or LangGraph
  agents. Use for test strategy, regression tests, fixtures and test doubles,
  integration or contract boundaries, flaky tests, and deciding what is not
  worth testing. Optimize for failure detection and operational confidence,
  not coverage targets or tests that merely mirror implementation. Do not use
  for non-Python test frameworks or load and performance testing alone.
---

# Pytest

Write the smallest maintainable test portfolio that would stop a credible
production regression. Tests are executable risk controls, not proof that lines
ran. Every test must protect a behavior, invariant, failure mode, compatibility
surface, or previously observed bug.

## Non-negotiable standard

- Be able to finish this sentence before adding a test: **"This test fails if
  ..."** The answer must describe a meaningful regression, not a changed private
  implementation or uncovered line.
- Assert observable behavior: returned values, public errors, protocol data,
  persisted state, emitted messages, idempotency records, or another stable
  effect. Assert calls only when the interaction itself is a contract, such as
  no charge before approval or exactly one acknowledgement.
- Use the cheapest boundary that faithfully exercises the suspected failure.
  Do not replace a database, broker, framework lifecycle, serializer, or model
  provider and then claim that integration with it works.
- Keep the default suite hermetic: no developer credentials, shared staging
  state, paid models, or accidental network. Live checks are explicit, bounded,
  marked, and selected by a separate command or job.
- Make failures reproducible. Control clocks, IDs, randomness, scheduling, and
  external responses. Use bounded waits on observable conditions; never use a
  sleep as the assertion mechanism.
- Do not add weak assertions, duplicate tests, snapshots of incidental output,
  or framework self-tests to raise coverage. Coverage is a map for finding
  questions, not a test-quality score or completion criterion.
- Preserve the repository's supported Python and dependency versions, test
  layout, async plugin, marker vocabulary, and CI commands unless changing them
  is part of the request.
- A request for tests does not by itself authorize production refactors, new
  dependencies, live-provider calls, or CI changes. Use existing seams first;
  explain a missing seam and request the necessary scope when production code
  must change.

## Proportionate discovery

Inspect enough context to make the requested decision accurately. A narrow
regression test may need only the owning behavior, direct collaborators, nearby
fixtures, and targeted command. A suite design, integration change, or broad
review needs the wider discovery below:

1. Inspect the production behavior, public entry points, dependency boundaries,
   configuration, and lifecycle. Trace the success path and the credible
   failures, including partial effects and retry behavior.
2. Inspect `pyproject.toml` or equivalent pytest configuration, lock files,
   plugins, existing tests, fixture scopes, markers, warning policy, coverage
   configuration, and the exact local and CI commands. Do not copy examples for
   a different installed framework version.
3. Classify each real dependency: in-process collaborator, database, filesystem,
   HTTP service, broker or worker, clock, random source, model provider,
   checkpointer, or whole deployed process.
4. Look for production evidence: incidents, bug reports, migrations, provider
   changes, concurrency promises, security requirements, and compatibility
   contracts. These determine test priority.
5. Identify what is already proved at a cheaper layer. Do not repeat the same
   branch matrix through unit, API, integration, and E2E tests.

When the requested behavior or oracle is genuinely unspecified, surface that
gap rather than inventing a contract from the current implementation.
If production code or locked configuration is unavailable for an advisory
request, do not pretend it was inspected: return clearly labeled scaffolding,
list the discovery facts still needed, mark version-sensitive assumptions, and
do not claim that example code ran.

## Make a risk-to-proof map

When designing or reviewing a suite (not for a single regression test), a
compact matrix is a useful heuristic before implementation:

| Behavior or risk | Regression the test catches | Stable oracle | Cheapest faithful profile | Controlled or real dependencies |
| --- | --- | --- | --- | --- |

Drop or redesign any proposed test whose regression, oracle, or boundary cannot
be explained. Prioritize irreversible effects, money or permissions, data loss,
security boundaries, compatibility, retries, concurrency, and common user
journeys over getters, constructors, and incidental branches.

## Select the proof boundary

Choose by what the test must execute to expose the defect:

- **Unit:** wholly in process and deterministic. Exercise domain rules,
  application actions, parsers, routers, graph nodes, and concrete adapters with
  a fake of their direct external collaborator.
- **Component or API slice:** exercise the in-process application boundary while
  deliberately replacing outer effects. In repositories that group these under
  `unit/`, preserve that convention and describe the boundary accurately.
- **Contract:** verify an externally consumed compatibility surface such as a
  schema, serialized message, package export, configuration document, or
  provider/client conformance without claiming the live system works.
- **Framework characterization:** a contract test that pins third-party
  behavior the application relies on; design rules are in
  [references/core-principles.md](references/core-principles.md#framework-characterization).
- **Integration:** run a concrete adapter against a real disposable
  implementation: the production database dialect, broker, filesystem,
  checkpointer, protocol endpoint, or service emulator.
- **End to end:** start the deployable and prove a small number of critical
  journeys across its real internal boundaries.
- **Live:** call a shared or paid external provider. Keep this opt-in and treat
  it as current-provider compatibility or an evaluation, not a deterministic
  unit test.

Move upward only when the lower boundary cannot expose the intended defect.
Keep a higher-level test when its wiring, lifecycle, serialization, process, or
real-infrastructure coverage adds distinct confidence.

Directory placement, profile classification, markers, CI selection, and where
shared test-support types live are owned by `$python-service-architecture`:
[testing.md](../python-service-architecture/references/testing.md#profiles-and-markers)
("Profiles and markers", "Fixtures and static data", "Test support packages"). This skill owns test design, doubles,
assertions, async, and flakiness. For telemetry tests see
`../otel-observability/references/testing.md`; for settings tests and settings
fixtures see `$python-settings-config` (`../python-settings-config/SKILL.md`).

## Required references

Read [references/core-principles.md](references/core-principles.md) for every
task using this skill. Then read only the references relevant to the system:

- Read
  [references/integration-boundaries.md](references/integration-boundaries.md)
  for any database or SQLAlchemy test (it owns the database rules for every
  framework), filesystem, subprocess, external-service, contract, E2E,
  skip/xfail, or CI job design.
- Read [references/fastapi.md](references/fastapi.md) for FastAPI or Starlette
  request tests, ASGI lifespan, async clients, dependency overrides, streaming,
  WebSockets, or sessions injected through FastAPI dependencies.
- Read [references/workers.md](references/workers.md) for asyncio worker loops,
  database-backed work queues, task queues such as Celery or RQ, consumers,
  schedulers, retries, acknowledgements, duplicate delivery, or worker-process
  integration.
- Read
  [references/langchain-langgraph.md](references/langchain-langgraph.md) for
  LangChain agents, LangGraph graphs, tools, model fakes, state, checkpointing,
  interrupts, streaming, live providers, or evals.

When producing concrete code, fixtures, or pytest configuration, read the
matching example reference or references. A task that genuinely crosses domains
may require more than one; do not load unrelated examples:

- [references/examples-core.md](references/examples-core.md) for plain Python
  units, recording fakes, typed builders, bounded waits, async fixtures,
  parametrization, Hypothesis, the test-database engine fixture, or the async
  and sync SQLAlchemy same-connection transaction fixtures;
- [references/examples-fastapi.md](references/examples-fastapi.md) for FastAPI
  or async ASGI patterns;
- [references/examples-workers.md](references/examples-workers.md) for asyncio
  worker loops, database work queues, Celery task adapters, or worker round
  trips;
- [references/examples-langchain-langgraph.md](references/examples-langchain-langgraph.md)
  for scripted tool-calling models, graph routing, checkpoint isolation, or
  interrupt/resume.

For strategy-only work, load an example only when it materially clarifies the
recommendation. Examples are scaffolding, not project contracts; adapt them to
the repository's APIs and installed versions.

## Writing workflow

1. Name the behavior in domain or protocol language. Prefer names such as
   `test_duplicate_delivery_does_not_charge_twice` over names that repeat a
   method name.
2. Choose the stable oracle before arranging doubles. A test with no meaningful
   oracle is not rescued by elaborate setup.
3. Arrange only facts relevant to the behavior. Use typed builders or explicit
   values when a fixture would hide the scenario; fixture rules are in
   [core-principles.md](references/core-principles.md#fixtures-reveal-ownership-and-cost).
4. Perform one meaningful action. Multiple calls are appropriate when the
   behavior is inherently sequential, such as retry, idempotency, resume, or
   state-machine behavior.
5. Assert one behavior's complete semantic outcome, including the absence of
   dangerous partial effects, with exact values for deterministic results. Do
   not assert every field merely because it exists. Business outcome, emitted
   telemetry, and framework graph shape are separate behaviors: separate tests
   share the harness, not the assertions. A name joining independent outcomes
   with `_and_` signals a split; sequential protocols are exempt. This is not a
   one-assert-per-test rule.
6. Put the test at the narrowest owner and fixture scope. Prefer one behavioral
   owner and execution profile per module; split a mixed module when the
   distinction affects setup, selection, or readability.
7. Prove test sensitivity when practical. A regression test should fail against
   the known broken behavior; new behavior should have a meaningful red phase;
   a controlled collaborator can force the error branch. Never leave temporary
   mutations in production code.
8. Run the smallest useful test command, then the containing profile and any
   affected integration or contract command. Expand verification in proportion
   to the change and risk.

## Quality gate

Reject or rewrite a test that does any of the following without a specific
contractual reason:

- patches or reimplements the subject under test, or reimplements production
  control flow in the test;
- asserts only that a mock returned what the test configured it to return;
- locks private helper calls, incidental call order, log prose, generated IDs,
  timestamps, token chunks, or full natural-language responses (valid
  structured-log oracles:
  [core-principles.md](references/core-principles.md#oracles));
- checks a framework, Pydantic, SQLAlchemy, Celery, or LangGraph feature without
  exercising application-owned policy or wiring, outside the
  [framework characterization](references/core-principles.md#framework-characterization)
  profile;
- broadens fixtures or uses distant `autouse` setup to make dependencies less
  visible;
- shares mutable state, a fake with a call counter, a checkpointer, a database
  row, or a queue across tests without deterministic isolation;
- silently skips because required integration infrastructure is absent
  ([`require_env`](references/core-principles.md#suite-hygiene));
- relies on retries to conceal flakiness, arbitrary sleeps, execution order, or
  an unbounded wait;
- marks a known bug or dependency limitation `xfail` without a reason with an
  owner or issue, a narrow condition, the expected failure type, and strict
  unexpected-pass (XPASS) behavior;
- duplicates a lower-level behavior matrix at a more expensive layer;
- exists only to hit a line, branch, percentage, or test-count target.

### Mechanical checklist

Grep for these in every new or reviewed test. Each is a defect unless the test
states the contractual exception. The full rules are in the linked
[core-principles.md](references/core-principles.md) sections; items without a link are stated only here.

- Waits and time ([rules](references/core-principles.md#make-time-randomness-and-concurrency-observable)):
  a bare `.wait()`, `await task`, `await queue.get()`, or future await outside
  `asyncio.timeout(...)`; `while ...: await asyncio.sleep(0)` or any poll
  outside the one bounded `wait_until` helper; `time.sleep` or `asyncio.sleep`
  in a unit test.
- Doubles ([rules](references/core-principles.md#doubles-must-be-correct)): `assert` inside a double; a
  spec-less `Mock`/`AsyncMock` for a port, or `call_args` echoed back into the
  expected value; `SimpleNamespace` for a typed collaborator or constructible
  library type ([missing seam](references/core-principles.md#stop-at-a-missing-seam)); `cast(Any, ...)`,
  `object.__new__(Subject)`, or `# type: ignore` to force a double to fit
  (general rule: `$python-code-conventions`,
  `../python-code-conventions/SKILL.md` "Type escape hatches").
- Oracles: an asserted value that no code path under test writes; an assertion
  on a local literal, the environment (`datetime.now().year`), or `is not None`
  on a factory that cannot return `None`; an expected value computed with the
  production expression; `pytest.raises((A, B))` unless the contract is a union
  and says so; a rejection test without `match=` or an attribute check
  identifying the reason, including every case of a parametrized rejection
  table; a compound `assert x is not None and x.y == ...` (narrow on its own
  line).
- Private `._x` access or calls, unless the test declares itself an explicit
  white-box contract.
- Parameters ([rules](references/core-principles.md#parametrization)): a non-trivial parameter table
  without `pytest.param(..., id=...)`, an unused parameter, or a test body
  branching on a parameter (split success and failure).
- Fixtures ([rules](references/core-principles.md#typed-fixtures-and-builders)): a fixture returning
  `Any`, a tuple, a module, or a class or function only so tests can reach it.

When the requested review or refactor explicitly includes test removal, delete
redundant or misleading tests only when actual risk coverage is preserved or
improved. Otherwise report them as candidates and leave them unchanged. Test
code is production code: type it, include tests and test support in the mypy
run, keep helpers cohesive, and make failures readable to the engineer on call.

## Verification and handoff

Report:

- the behaviors and failure modes now protected;
- the exact commands run and their collected, passed, failed, skipped, xfailed,
  and xpassed outcomes;
- which dependencies were fake, disposable-real, deployed-real, or not tested;
- any tests not run and the concrete prerequisite;
- remaining risks that need a different boundary, live provider, load test,
  security review, or production observability.

Never claim that an integration, migration, worker, checkpoint, live-provider,
or E2E path is covered when only a unit substitute ran.
