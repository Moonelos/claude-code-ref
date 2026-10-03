---
name: python-service-architecture
description: >-
  Design, scaffold, refactor, or review modules and tests inside a Python backend
  service or internal library. Use for application/domain/port boundaries,
  adapters, bootstrap, HTTP APIs, workers and queue consumers, GenAI code,
  persistence ownership, and test profiles. Use `python-repository-setup` for
  top-level workspace and tooling decisions, and domain-specific skills for
  implementation mechanics.
---

# Python Service Architecture

A service's **business core uses strict hexagonal architecture with no
forwarding layers**. Every business feature has the same fixed shape, so an
agent always knows where new code goes and a reviewer always knows where to
look. `application/` reads as the catalog of everything the service does.
Code that is not a business operation (the internals of a GenAI capability,
technical maintenance jobs, provider setup) takes the direct shape in
[Where the hexagon applies](#where-the-hexagon-applies). Import rules are
enforced by tools; ownership rules by review and tests.

Non-deployable packages use the lighter shared-library structure
([shared-libraries.md](references/shared-libraries.md)); never copy a service
shell into a library.

## The feature shape

```text
api/ or workers/           entry point: parse input → call ONE action → map the result
application/<resource>.py  the one-call actions of one resource; the catalog
application/<operation>.py an action with its own steps, plus siblings sharing its helpers
domain/                    pure types and decisions, no I/O; imported directly
ports/<capability>.py      Protocol + its result types + its errors
db/ | adapters/ | genai/   the class implementing a port; owns the integration
bootstrap/                 builds every implementation once and runs the process
```

`application/<resource>.py` holds the one-call actions of one resource
(`application/conversations.py`: create, list, detail, history). An action with
its own steps gets `application/<operation>.py`, together with the sibling
actions that share its private helpers (`retry_turn` beside `submit_turn`).
Never one file per one-call action. Both kinds of module are the catalog.

A request travels `entry point → action → implementation`. The worked example is
[templates.md](references/templates.md#canonical-feature), and an executable
version is in [`assets/canonical_service/`](assets/canonical_service/).

## Reference routing

For a deployable service read [templates.md](references/templates.md),
[boundaries.md](references/boundaries.md), [domain.md](references/domain.md),
[errors.md](references/errors.md), and [testing.md](references/testing.md). For
an internal library read [shared-libraries.md](references/shared-libraries.md)
and [testing.md](references/testing.md) instead. Load the rest when they apply:

- [api-and-workers.md](references/api-and-workers.md): HTTP API, worker,
  scheduled process, queue consumer, or hybrid.
- [persistence.md](references/persistence.md): state transitions, concurrent
  writes, a unit of work, or writes to an external system; skip for ordinary
  reads.
- [async-and-lifecycle.md](references/async-and-lifecycle.md): async I/O or
  long-lived resources.
- [ai.md](references/ai.md): LLM calls, agents, graphs, prompts, AI tools.
- [modularization.md](references/modularization.md): splitting or migrating an
  existing service.

Language idioms and size signals are owned by `python-code-conventions`
(fallback: `../python-code-conventions/SKILL.md`).

## Where the hexagon applies

Decide the shape per piece of code before placing it. The full feature shape
pays for itself where a fake port tests real orchestration and the action
catalog answers "what does this service do?"; elsewhere it only adds hops.

| Code | Shape | Why |
| --- | --- | --- |
| Business operation: reached by a route, worker, or CLI, or changes business state (turns, conversations, feedback, submissions) | Full: entry point → action → port → implementation | The catalog and the enforced import boundary earn their cost here; a faked port earns it in tests of actions that orchestrate ([boundaries.md](references/boundaries.md#when-a-port-earns-its-cost)) |
| Internals of a GenAI capability: retrieval, query rewrite, embeddings, read-only tools, middleware | Direct: classes and functions in the agent's folder or a capability folder (`genai/retrieval/`), with the fixed file names of [ai.md](references/ai.md#standard-agent-shape), called directly; no action, no application port ([ai.md](references/ai.md#when-a-tool-calls-an-action)) | Only the agent reaches them; the capability's own port (`AnswerAgent`) is already the boundary tests fake |
| Technical maintenance job (retention purge, cleanup sweep) whose rule no other entry point needs | Direct: one function in the integration that owns the data (`db/retention.py`) run by the supervisor; no `domain/`, port, or action ([api-and-workers.md](references/api-and-workers.md#technical-jobs)) | Nothing else calls it, and its tests need the real database anyway |
| Provider or SDK client setup | Inside the agent's `llms.py` or the adapter constructor ([ai.md](references/ai.md#ownership-inside-genaitask)) | Construction policy, not a capability |

Promote direct code to the full shape when a trigger holds **today**: a second
entry point needs it, it starts making business decisions or writes, or an
action test must fake it. "It does I/O" alone is not a trigger.

## Core rules and why

1. **Every business operation is one action in `application/`, even a one-line
   read.** A step that only an agent tool reaches is not a business operation
   ([Where the hexagon applies](#where-the-hexagon-applies)). *Why:* the
   catalog stays complete, so "what does this service do?" has one answer, and
   a new entry point has an obvious thing to call.
2. **Every business entry point calls exactly one action.** Routes live in
   `api/`; loops and queue consumers in `workers/`. Technical endpoints and
   jobs call none
   ([api-and-workers.md](references/api-and-workers.md#health-and-readiness)).
   An agent tool calls an
   action only when it triggers a business operation
   ([ai.md](references/ai.md#when-a-tool-calls-an-action)). *Why:* business
   logic in an entry point is invisible to every other entry point, and gets
   duplicated or skipped.
3. **Dependencies point inward** ([boundaries.md](references/boundaries.md#the-core-rule)).
   `application/` imports `domain/`, `ports/`, and `observability/`; never
   `api/`, `workers/`, `bootstrap/`, `config/`, `db/`, `adapters/`, or `genai/`.
   *Why:* business rules can then be read, tested, and changed without a
   database, SDK, or framework in the room.
4. **Every I/O capability an action uses is a port, one per capability**
   (`SubmissionStore`, not a Protocol per table, nor one store for every table
   the service owns; see [boundaries.md](references/boundaries.md#application-ports)).
   *Why:* the action states what it needs in business terms, and tests can fake
   exactly that.
5. **Pure logic is never behind a Protocol.** Decisions, validation, parsing,
   and calculations live in `domain/` and are imported directly
   ([domain.md](references/domain.md)). *Why:* a Protocol around a pure function
   adds a fake to every test and proves nothing a direct unit test would not.
6. **No layer only forwards.** No handler classes in bootstrap, no `db/`
   coordinator that opens a transaction and calls a same-named method, no
   re-export modules. The one-call action of rule 1 is the single exception,
   and it is complete as written: do not introduce DTOs, mapping, helpers,
   logging, or tests solely to give it additional substance, and avoid unit
   tests that only assert delegation to a fake. Verify meaningful behavior at
   the boundary that owns it.
   *Why:* every hop is code to read and change, and a hop with no behavior
   hides where the behavior actually is.
7. **Implementations translate once.** The class implementing a port hides the
   SDK, returns the port's types, and raises the port's errors
   ([errors.md](references/errors.md)). *Why:* callers handle one failure
   vocabulary, and an unknown failure is never relabelled as an outage.
8. **Each concrete integration has one home:** HTTP in `api/`, persistence in
   `db/`, LLM code in `genai/`, every other external system in `adapters/`.
   There is no root `messaging/`, `core/errors.py`, or `constants.py`.
   *Why:* one home per technology means one place to review it.
9. **Errors, constants, and settings follow their owner**
   ([boundaries.md](references/boundaries.md#errors-and-constants-follow-ownership)).
   *Why:* a shared dump grows until nobody owns anything in it.
10. **Bootstrap builds each implementation once and knows nothing about what
    they do.** *Why:* wiring and behavior change for different reasons; mixed,
    both become hard to test.
11. **Nothing speculative.** Create only the directories, Protocols, and
    packages the service needs today; the trees in the references are placement
    maps, not checklists. *Why:* "we may need it" structure is paid for on every
    read and rarely used.
12. **All imports are absolute** (Ruff `TID252`); `config/` holds Python
    settings code, not YAML (`python-settings-config`, fallback:
    `../python-settings-config/SKILL.md`).

A Protocol that is not an application port (the API's runtime view, a
library-to-service callback) needs a trigger that holds today
([boundaries.md](references/boundaries.md#when-a-port-earns-its-cost)).

## Decisions that look ambiguous

**Who runs a state transition.** The decision is always a pure function in
`domain/`; the only question is who holds the transaction. Choose it from
[persistence.md](references/persistence.md#choose-the-transaction-owner),
preferring one port method over a unit of work. Every committed intermediate
state (`PENDING` before a carrier call) has a named exit.

**Entry points pass collaborators explicitly.** A route or worker passes fields
of the runtime view to the action as keyword arguments. The cost: adding a port
to an action changes every entry point that calls it. The benefit: each call
site shows what the operation touches, and the type checker verifies the
wiring. Do not remove the cost with a DI container, handler classes,
`functools.partial` over actions in bootstrap
([boundaries.md](references/boundaries.md#bootstrap)), or one FastAPI provider
per port.

**Steps shared by several actions** are private helpers, never catalog entries
or entry-point targets
([boundaries.md](references/boundaries.md#action-boundaries-a-deliberate-cost)).

**Port failures that drive a business outcome.** When a port failure decides
the outcome (model unavailable → human review), the action maps the port error
to a domain value (`ClassificationFailure.UNAVAILABLE`) and the domain decision
chooses the status and reason; `domain/` never imports port errors.

**Preconditions a decision relies on.** When a domain decision assumes a fact
about the caller (the actor is a manager), the action checks it or passes it
in as a value the decision checks. A route dependency may reject earlier for a
fast 403, but never as the only guard: the next entry point would skip it.

## Enforcement

Every service has import-linter contracts in pre-commit and a CI job that runs
the same hooks (create the job when the service is created, including when the
repository has no CI yet), for rule 3, pure
`domain/` and `ports/`, entry points importing no concrete integrations, and
only entry points importing `bootstrap/`. The contracts name every canonical
boundary whether or not it exists yet (`python-repository-setup`, fallback:
`../python-repository-setup/references/pre-commit.md`, "Architecture
contracts"). Libraries have independence contracts
([shared-libraries.md](references/shared-libraries.md#enforcement)).
`python-service-architecture-audit` adds static candidates and semantic review.

Must/never rules are mandatory; approximate numbers (~40 lines, ~10
collaborators) are review signals. Verification differs by rule:

| Verification | What it establishes |
| --- | --- |
| Static | Forbidden imports, obvious I/O, contract coverage; candidates for redundant layers |
| Semantic | Action boundaries, meaningful composition, policy and error ownership |
| Behavioral | Atomicity, idempotency, concurrency, rollback, recovery of intermediate states |

## Required discovery

Before proposing or changing a structure:

1. Inspect the actual package tree, entry points, imports, tests (collection
   config, markers, fixtures, CI selection), and deployment. Do not infer
   architecture or test type from filenames alone.
2. Classify the member as a deployable service or an internal library.
3. List the business actions and the I/O capabilities each one uses.
4. For each feature, trace the hops from entry point to SQL or external call and
   name any hop that only forwards.
5. Preserve repository conventions unless changing them has a clear, stated
   benefit. Never reorganize unrelated services for symmetry.
6. Before copying plumbing, look for an existing library or implementation to
   reuse ([shared-libraries.md](references/shared-libraries.md#extraction-triggers)).

## Implementation checks

Before coding each feature, decide from the brief's actual operations: the
transaction owner and concurrency guard for each state change, the recovery
path after a crash between a commit and an external write, how each provider or
driver outcome maps to a port result or error, and which action, item, or
process boundary handles each one. Keep the answers in your reasoning or the
handoff, not in files or extra modules; the owning references are
[persistence.md](references/persistence.md), [errors.md](references/errors.md),
and [api-and-workers.md](references/api-and-workers.md). Test each failure or
recovery path you decided, not only the happy path, and report which database,
broker, or provider guarantee remains unverified.

## Output and implementation behavior

For a design or review, provide:

1. The target source and test tree, containing only the directories needed.
2. The list of application actions, their entry points, and the ports each uses.
3. Violations, forwarding layers to remove, and the smallest coherent migration
   sequence.

For implementation, move one coherent boundary or feature at a time; update
imports, entry points, fixtures, markers, and CI selectors; and run focused tests
after each slice. Preserve behavior during a structure-only refactor.

## Related skills

- `python-repository-setup`: workspace members, `pyproject.toml`, lockfiles,
  pre-commit (including architecture contracts), Docker builds.
- `python-code-conventions`: language idioms and size signals.
- `python-settings-config`: settings and secrets.
- `python-sqlmodel-alembic`: SQLModel, repositories, transactions, Alembic.
- `otel-observability` and `python-logging`: tracing, metrics, logging.
- `pytest` for test design; `python-service-architecture-audit` for audits.
