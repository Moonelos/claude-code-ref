---
name: python-service-architecture-audit
description: >-
  Audit architectural drift inside an established Python backend service, and
  repair it when the user asks. Use for hexagonal dependency violations,
  misplaced modules, leaking framework contracts, speculative ports,
  centralized errors, GenAI boundary problems, duplicated cross-service
  infrastructure, or the final verification of a structural refactor. Do not
  use for ordinary feature edits that do not change or review service
  boundaries.
---

# Python Service Architecture Audit

Find architectural defects from repository evidence, separate enforceable
violations from judgment calls, and report them with a recommended route. This
skill owns the audit procedure; `python-service-architecture` owns the
structure and ownership rules. Cite its sections instead of restating them
(fallback path: `../python-service-architecture/references/<file>.md`).

## Required context

Read the `python-service-architecture` skill and the references it routes for the
service under review. Inspect the real source tree, imports, application entry
points, ports, concrete implementations, bootstrap wiring, tests, and runtime
configuration. Never infer architecture from filenames alone.

Run the bundled static checks against the import package. Pass `--workspace`
in a multi-member repository to find byte-identical modules in other members:

```bash
python scripts/audit_service.py path/to/src/package [--workspace path/to/repo]
```

Every hit cites the rule that owns it. Treat hits as **candidates to confirm**
by reading the code, not verdicts: `VIOLATION` marks import-direction and
placement hits that are nearly always real, `REVIEW` marks prompts for semantic
inspection. A clean run prints `static checks passed; semantic audit pending`.
Report the result as **static checks**, never as the result of the audit as a
whole; a clean run does not reduce the semantic work below.

Before tracing individual paths, inventory every public application action and
long-running process runner. For each one, record its input and output contract,
caller, injected collaborators, business decisions, external effects, and the
owner of any loop or lifecycle. Use that inventory to ensure a healthy action
does not hide drift in an uninspected sibling. Then trace every action far enough
to assign its decisions and effects to owners, with at least one complete
process-to-implementation trace for each distinct external capability family.

## Dependency audit

Search imports and verify each item against the named section of
`boundaries.md` unless another file is named. Items marked (script) are also
checked statically.

- `domain/` and `ports/` import no adapters, bootstrap, API, DB, GenAI, config,
  SDKs, or ORM packages (script) — The core rule.
- `application/` imports no concrete adapters, DB, GenAI, bootstrap, or config
  (script). It may use the service's own `observability/` helpers but never
  `opentelemetry` types (script) — `observability/`.
- `api/`, `adapters/`, `db/`, and `genai/` never import `bootstrap/` (script);
  bootstrap is the composition root and nothing but entry points imports it.
- API handlers and inbound adapters call public application entry points;
  adapters, repositories, and GenAI implementations depend inward on ports.
- Ports represent I/O or nondeterministic capabilities, not deterministic
  parsers, calculators, formatters, or business rules; they are named for the
  caller's need, not the current technology — When a port earns its cost.
- No concrete broker implementation lives in a root `messaging/` package.
- Every LLM, agent, prompt, AI schema, tool, or graph lives below root `genai/`;
  bootstrap calls GenAI factories with resolved configuration, and GenAI modules
  construct no runtime handles and read no settings at import time — `ai.md`,
  Factories and bootstrap wiring.
- No generic root or `core/` constants or errors module mixes unrelated owners;
  deployment-varying values live in `config/` — Errors and constants follow
  ownership (script flags the generic filenames).
- Small packages stay flat across every boundary; provider identity alone does
  not justify a folder — Flat-first growth across boundaries (script flags
  one-module adapter subpackages).
- No deployable imports another deployable's private package.
- No Python file uses a relative import (script).
- Tests can replace costly boundaries with small typed fakes without patching
  SDK internals — `testing.md`.

## Semantic audit

Trace real business actions from their process boundary through application
code, ports, concrete implementations, and bootstrap. For each trace, check the
owning rule:

| Check | Owner |
|---|---|
| Port contract: caller-needed capability, no framework verbs, vendor types, `Any`, or configuration controls | `boundaries.md` When a port earns its cost; Contract ownership |
| Implementations translate SDK failures into port-owned errors once, without a central translator mapping unrelated owners. Shared transient/permanent bases are allowed | `errors.md` Translate once; Classification bases |
| **Port failure with no handler:** every failure a port can raise reaches a named API or loop boundary | `errors.md` Handling boundaries |
| Errors, constants, validation, and helpers stay with their semantic owner | `boundaries.md` Errors and constants follow ownership |
| Repositories and adapters apply caller-owned decisions rather than choosing statuses, codes, messages, or transitions | `boundaries.md` Repositories apply decisions |
| Loops, stop events, sleeps, task creation, and shutdown stay in the supervisor; the single-iteration action stays in `application/` | `api-and-workers.md` Long-running worker |
| **Broker adapters map outcomes to ack/nak/terminate; they don't own retry policy** | `api-and-workers.md` SQS, Kafka, or another broker |
| Inbound API, broker, and SDK payloads are translated at the process adapter | `boundaries.md` Validate external structure |
| Application actions receive capability implementations. Raw handles go only into genai/adapter constructors | `boundaries.md` Constructor contracts |
| GenAI tasks own model binding, prompts, schemas, tools, and the capability adapter. A few cohesive tools may share `tools.py` | `ai.md` Standard agent shape; Tools and MCP |
| Application telemetry goes through the service's `observability/` vocabulary | `boundaries.md` `observability/` |
| **Pass-through wrappers:** a class or function that only renames a call adds no owner | `python-code-conventions` Constructors and wrappers |
| Package depth and abstractions are justified by current ownership, change, or test pressure | `boundaries.md` Flat-first growth across boundaries |

Procedure notes the rules do not cover:

- An action method that only delegates an intent-named operation (`complete`,
  `fail`, `expire`, `approve`) is a review prompt, especially when the concrete
  DB or adapter chooses the outcome.
- Inspect DTO fields recursively rather than trusting a wrapper named `domain`
  or `command`; delivery metadata (receipt handles, acknowledgements, topics,
  partitions, provider messages, raw requests) must not reach application,
  domain, or ports.
- Search for unused ports and protocols, but inspect callers before recommending
  deletion. Structural typing, a passing type checker, and test fakes do not
  prove that a port is technology-neutral or useful.
- For each action, compare its focused unit tests with its integration tests.
  Missing unit coverage is not itself a violation, but if business outcomes can
  only be shown through a real DB, broker, model, or SDK, check whether policy
  has escaped into that implementation.

Summarize the semantic pass with a compact ownership matrix containing, as
applicable: action, business decision, boundary input, port, concrete
implementation, state-transition owner, and lifecycle owner. Label
static-script findings separately from semantic findings.

## Shared-capability review

In a workspace, compare the reviewed service's technical plumbing with existing
libraries and matching code in other members. Search explicitly for overlapping
modules, identical function names, and service-local copies of capabilities a
shared library already provides. This comparison is read-only; it does not
authorize repairs to siblings. Read
`../python-service-architecture/references/shared-libraries.md` when a
candidate emerges, and `../otel-observability/references/setup/shared_library.md`
for repeated provider lifecycle, logging processors, or propagation policy.

A duplicate that meets the extraction trigger in `shared-libraries.md` is a
**Violation** to resolve; other justified extractions are **Improvements**, and
code that differs in meaning, lifecycle, or dependencies stays local.

For each candidate, report the source paths and consumers, shared operational
meaning, actual differences, minimal public inputs, service-local policy,
dependency and lifecycle costs, and the smallest consumer-by-consumer
migration. Environment, YAML, secrets, and service settings stay service-owned
and are mapped by bootstrap. Do not recommend generic shared dumping grounds or
wrappers that merely rename SDK calls. Textual similarity alone cannot
establish semantic reuse.

## Classification

Classify every finding as:

- **Violation:** dependency direction, contract leakage, or ownership is wrong.
- **Improvement:** a different shape materially improves isolation or navigation.
- **Preference:** cosmetic difference without architectural consequence.

Do not present preferences as violations.

When the service has no persistent architecture-fitness test, recommend one as
an Improvement: import-boundary contract tests in the service's own suite,
built on a shared AST inspector that has its own mutation or sensitivity tests
proving each check fails on a planted violation. The bundled script is a
one-shot aid, not a substitute. Test placement: `testing.md`.

## Report and route

By default the audit is **report-only**. Report the static checks, the semantic
findings with evidence and classification, the ownership matrix, the
shared-capability conclusions, and one recommended route:

- **No actionable findings:** state the checks run and the remaining
  uncertainty.
- **Plan first:** numerous findings, coordinated changes across boundaries or
  consumers, shared-library extraction, state-transition or compatibility
  changes, or material design uncertainty. Count alone does not decide; one
  consequential finding can require a plan.
- **Focused repair:** few findings whose fixes are local, understood, and
  reversible.

Write files or change code only when the user asks for repair:

- **Plan first:** invoke `openspec-propose` (fallback
  `../openspec-propose/SKILL.md`) to create the proposal, delta specs, design,
  and tasks, including evidence, classification, acceptance criteria,
  shared-capability conclusions, migration order, and verification tasks. Stop
  after presenting the planning artifacts; implementation waits for a new
  request. If the workflow is unavailable, explain the blocker and report the
  findings instead of implementing unplanned changes.
- **Focused repair:** create `FEEDBACK.md` at the reviewed repository root
  before editing code (if it exists, preserve it and use an unused descriptive
  name such as `worker-architecture-FEEDBACK.md`). Record each finding's
  classification, evidence, intended fix, and verification steps as `- [ ]`
  checkboxes; tick one only after its fix and checks pass. Move one coherent
  boundary at a time, update all consumers, add or strengthen behavior or
  contract tests for the defect, and run focused tests before the full suite.
  Record the completion-gate results and any unchecked work in the same file.

Keep repairs scoped to the reviewed service and its necessary consumers. If a
focused repair reveals a need for coordinated design, keep the feedback file
and completed work, and route the rest through planning.

## Completion gate

Before declaring a structural repair complete:

1. rerun `scripts/audit_service.py`;
2. run the service's architecture-fitness tests;
3. run formatting, lint, type checking, and the relevant test profiles;
4. report remaining semantic risks that static checks cannot prove.

Never claim that the audit proves port usefulness, error ownership, bootstrap
composition, or runtime behavior when only static imports were checked.
