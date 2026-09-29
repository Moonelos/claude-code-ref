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

Services use **strict hexagonal architecture with no forwarding layers**. Every
feature has the same fixed shape, so an agent always knows where new code goes
and a reviewer always knows where to look. `application/` reads as the catalog
of everything the service does. Import rules are enforced by tools; ownership
rules by review and tests.

Non-deployable packages use the lighter shared-library structure
([shared-libraries.md](references/shared-libraries.md)); never copy a service
shell into a library.

## The feature shape

```text
api/ or workers/           entry point: parse input → call ONE action → map the result
application/<action>.py    async def for one business operation; the catalog
domain/                    pure types and decisions, no I/O; imported directly
ports/<capability>.py      Protocol + its result types + its errors
db/ | adapters/ | genai/   the class implementing a port; owns the integration
bootstrap/                 builds every implementation once and runs the process
```

A request travels `entry point → action → implementation`. The worked example is
[templates.md](references/templates.md#canonical-feature), and an executable
version is in [`assets/canonical_service/`](assets/canonical_service/).

## Core rules and why

1. **Every business operation is one action in `application/`, even a one-line
   read.** *Why:* the catalog stays complete, so "what does this service do?"
   has one answer, and a new entry point has an obvious thing to call.
2. **Every entry point calls exactly one action.** Routes live in `api/`; loops
   and queue consumers in `workers/`; agent tools in `genai/`. Health, readiness,
   metrics, and version endpoints are technical and call none. *Why:* business
   logic in an entry point is invisible to every other entry point, and gets
   duplicated or skipped.
3. **Dependencies point inward** ([boundaries.md](references/boundaries.md#the-core-rule)).
   `application/` imports `domain/`, `ports/`, and `observability/`; never
   `api/`, `workers/`, `bootstrap/`, `config/`, `db/`, `adapters/`, or `genai/`.
   *Why:* business rules can then be read, tested, and changed without a
   database, SDK, or framework in the room.
4. **Every I/O capability an action uses is a port, one per capability**
   (`SubmissionStore`, not a Protocol per table). *Why:* the action states what
   it needs in business terms, and tests can fake exactly that.
5. **Pure logic is never behind a Protocol.** Decisions, validation, parsing,
   and calculations live in `domain/` and are imported directly
   ([domain.md](references/domain.md)). *Why:* a Protocol around a pure function
   adds a fake to every test and proves nothing a direct unit test would not.
6. **No layer only forwards.** No handler classes in bootstrap, no `db/`
   coordinator that opens a transaction and calls a same-named method, no
   re-export modules. The one-call action of rule 1 is the single exception.
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
`domain/`; the only question is who holds the transaction.

| The operation | Transaction owner | The action's body |
| --- | --- | --- |
| Read, decide, and write atomically, including an outbox row the decision produces | One port method; the `db/` implementation locks, calls the domain decision, writes | One call to the port |
| Several writes the action must interleave with its own decisions or other ports | A unit-of-work port the action enters | Observe, call the domain decision, apply, commit |
| A database change plus a *write* to an external system (payment, shipment, email) | Nobody: they cannot share a transaction | Commit durable intent first; deliver through an outbox or handoff |
| A *read* from an external system or model, then a database write | Nobody needs one | Call first, then write once; no intermediate state |

A one-call action in the first row is correct: it is the operation's catalog
entry. Prefer the first row; use a unit of work only when the action itself must
decide between writes. Do not invent intermediate states: a classification,
lookup, or model call that changes nothing outside the service is not an effect
to protect. When an intermediate state does exist (`PENDING` before a carrier
call), it has a named exit: the step that completes it, a sweeper that retries
it, or an expiry ([persistence.md](references/persistence.md)).

**Entry points pass collaborators explicitly.** A route or worker passes fields
of the runtime view to the action as keyword arguments. The cost: adding a port
to an action changes every entry point that calls it. The benefit: each call
site shows what the operation touches, and the type checker verifies the
wiring. Do not remove the cost with a DI container, handler classes,
`functools.partial` over actions in bootstrap, or one FastAPI provider per port.

**Steps shared by several actions.** A step that two actions both run (triage a
ticket, ship one order) is not a catalog entry: put it in a private module
(`application/_shipping.py`) or in the module of the action that owns it, and
never call it from an entry point. An action that *is* a business operation in
its own right stays public, and another action may call it. A result type the shared step
returns and entry points read lives in `domain/` (or the public action's
module), never in the private module; actions reuse those types in their own
outcome unions rather than renaming them. A shared step propagates dependency
outages; each calling action decides whether an outage is an outcome for it
(the consumer retries this message later) or stops its batch (the sweeper).

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
the same hooks (create the job with the service when the repository has CI; say
so in the handoff when it has none yet), for rule 3, pure
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
