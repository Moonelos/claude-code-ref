---
name: python-service-architecture-audit
description: >-
  Audit architectural drift inside an established Python backend service or
  internal shared library. Use for hexagonal
  dependency violations, library kind and independence problems,
  misplaced modules, leaking framework contracts, forwarding layers, callable
  or per-repository Protocols, business logic outside application actions,
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
in a multi-member repository to find byte-identical modules in other members.
Test doubles are searched in `--tests` (default: the member's `tests/`, two
levels above a `src/<package>` root):

```bash
python scripts/audit_service.py path/to/src/package [--workspace path/to/repo] [--tests path/to/tests] [--allow-external PACKAGE ...]
```

`domain/`, `ports/`, and `application/` may import only the standard library,
`pydantic`, `typing_extensions`, `annotated_types`, and the service's own
package, and `application/` may also import `structlog` for a recorded
fallback; every other third-party import is flagged. Pass `--allow-external` for
a technology-neutral dependency the repository deliberately admits (for example
a shared contract library). The script also looks upward from the package for
the import-linter contracts and their `lint-imports` pre-commit hook.

Every hit cites the rule that owns it. Treat hits as **candidates to confirm**
by reading the code, not verdicts: `VIOLATION` marks import-direction and
placement hits that are nearly always real, `REVIEW` marks prompts for semantic
inspection. The script label is the confidence of the static match, not the
final classification: forwarding functions, `db/` coordinators, callable
Protocols outside `ports/`, and actions bound with `partial` in bootstrap are
printed as `REVIEW` because the script cannot prove the meaning is unchanged,
but once confirmed they are Violations ([Classification](#classification)).
The script sees only nominal implementations and name references: confirm a
"Protocol without an implementation" hit against structural implementations and
test doubles before reporting it. Contract coverage is reported once, listing
every unforbidden edge; a `REVIEW` there means only boundaries the service does
not have yet are missing. A clean run prints `static checks passed;
semantic audit pending`.
Report the result as **static checks**, never as the result of the audit as a
whole; a clean run does not reduce the semantic work below.

Before tracing individual paths, inventory every public application action and
every entry point (routes, workers, consumers, agent tools, CLIs). For each one, record its input and output contract,
caller, injected collaborators, business decisions, external effects, and the
owner of any loop or lifecycle. Use that inventory to ensure a healthy action
does not hide drift in an uninspected sibling. Then trace every action far enough
to assign its decisions and effects to owners, with at least one complete
process-to-implementation trace for each distinct external capability family.

## Dependency audit

Search imports and verify each item against the named section of
`boundaries.md` unless another file is named. Items marked (script) are also
checked statically.

- `domain/` and `ports/` import no adapters, bootstrap, API, workers, DB, GenAI,
  config, SDKs, or ORM packages (script) — The core rule.
- `application/` follows the internal allowances in The core rule: no
  `api/`, `workers/`, bootstrap, config, `db/`, `adapters/`,
  `genai/` (script), and never `opentelemetry` types (script) — The core rule;
  `observability/`. The repository enforces this with an import-linter contract
  in pre-commit and CI; its absence is a Violation (script checks that the
  contracts' source and forbidden modules cover all required invariants, whether
  written as `forbidden` or `layers` contracts, and that the pre-commit hook
  exists; confirm CI runs it by reading `.github/workflows/`, `.gitlab-ci.yml`,
  `buildkite/`, or the repository's documented pipeline, since the script does
  not. A repository with no CI at all gets one Violation for the missing CI
  step, not one per contract)
  (`../python-repository-setup/references/pre-commit.md`, "Architecture
  contracts").
- `api/` and `workers/` never import concrete `db/`, `adapters/`, or `genai/`
  code (script and import-linter contract) — The core rule.
- `api/`, `workers/`, `adapters/`, `db/`, and `genai/` never import
  `bootstrap/` (script); bootstrap is the composition root.
- Every business entry point (route, worker, consumer, agent tool, CLI) lives in
  `api/`, `workers/`, `genai/` (tools), or `main.py`, never in `bootstrap/` or
  `adapters/`, and calls exactly one application action and holds no business
  logic, including simple reads; port
  implementations depend inward on their ports — Application ports;
  `application/`. Technical endpoints (liveness, readiness, metrics, version)
  call no action and are not findings; one that reports business facts is a
  business entry point. A one-call action follows
  Action boundaries: a deliberate cost; confirm it is a real public operation.
- Every I/O capability an action uses is one port per capability, implemented
  directly by a class in `db/`, `adapters/`, or `genai/` (script flags ports
  without an implementation). Ports never model deterministic parsers,
  calculators, formatters, or business rules; a `__call__`-only Protocol
  standing in for a domain function or an application action is a Violation
  (script) even when a test fakes it: the triggers below apply to other
  Protocols. A unit-of-work factory whose `__call__` returns a context manager
  is a port, not a stand-in — Application ports; `persistence.md`.
- Protocols that are not application I/O ports meet a trigger: a test fakes it,
  a second implementation exists, a decorator wraps it, or a package may not
  import the implementation (script flags those with one implementation and no
  test reference) — When a port earns its cost.
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
| **Hop chain:** verify each boundary and additional collaborator owns the responsibility allowed by the rule; do not count calls as layers. Public one-call actions are allowed | `boundaries.md` No forwarding layers |
| **Logic outside actions:** input resolution, cursor decoding, selection building, batch-continuation decisions, or business loops in routes, workers, the supervisor, or `genai/` belong in the action or `domain/` | `boundaries.md` `application/`; `ai.md` Invocation and error translation |
| **Preconditions:** a fact a domain decision assumes about the caller (a role, ownership) is checked in the action, not only by one entry point | SKILL.md Decisions that look ambiguous |
| **Port granularity:** one port per capability; a Protocol per repository or table is merged | `boundaries.md` Application ports |
| **Mocks for pure logic:** a port mock whose assertions only inspect values computed by pure functions; move the logic to `domain/` and test it directly | `boundaries.md` When a port earns its cost |
| Contract: caller-needed capability, no framework verbs, vendor types, `Any`, or configuration controls | `boundaries.md` Contract ownership |
| Implementations translate SDK failures into port-owned errors once, without a central translator mapping unrelated owners. Shared transient/permanent bases are allowed | `errors.md` Translate once; Classification bases |
| **Port failure with no handler:** every failure a port can raise reaches a named API or loop boundary | `errors.md` Handling boundaries |
| Errors, constants, validation, and helpers stay with their semantic owner | `boundaries.md` Errors and constants follow ownership |
| Repositories and adapters apply caller-owned decisions rather than choosing statuses, codes, messages, or transitions | `boundaries.md` Repositories apply decisions |
| Tasks, cadence, stop events, failure policy, and shutdown stay in the supervisor; each iteration is a worker function in `workers/` that calls one action and logs its summary; bootstrap logs no business results | `api-and-workers.md` Long-running worker |
| **Consumers:** the inbox adapter moves messages and never names an action; the consumer worker maps the action's outcome to a settlement; neither owns retry policy | `api-and-workers.md` SQS, Kafka, or another broker |
| **Batches:** a per-item failure is recorded on that item; only a dependency outage stops the batch | `errors.md` Handling boundaries |
| **Failure classification:** credentials, missing endpoints, and misconfiguration are unavailable, not rejected; a 2xx with an unreadable body is an unknown outcome, never a failure; a corrupt stored row is not moved to a terminal business state | `errors.md` Classification bases; `persistence.md` Uncertain external writes |
| Inbound API, broker, and SDK payloads are translated at the process adapter | `boundaries.md` Validate external structure |
| Application actions receive capability implementations. Raw handles go only into genai/adapter constructors | `boundaries.md` Constructor contracts |
| GenAI tasks own model binding, prompts, schemas, tools, and the capability adapter. A few cohesive tools may share `tools.py` | `ai.md` Standard agent shape; Tools and MCP |
| Application telemetry goes through the service's `observability/` vocabulary | `boundaries.md` `observability/` |
| **Pass-through wrappers:** confirm static forwarding candidates have no boundary or behavior of their own; distinguish public actions from extra helpers | `boundaries.md` No forwarding layers |
| **Atomicity:** identify the transaction owner, concurrency guard, and DB/external-effect recovery contract; every committed intermediate state has a named exit; verify behavior with tests | `persistence.md` (load only for relevant writes) |
| Package depth and abstractions are justified by current ownership, change, or test pressure | `boundaries.md` Flat-first growth across boundaries |
| **Tool failures:** every error an agent tool's action can raise becomes a tool message or a task abort that the capability translates once; none escapes the capability's port | `ai.md` Tools and MCP |
| **Scope:** behavioral machinery (intermediate states, sweepers, outboxes, idempotency keys, extra loops) is required by the brief or by a rule whose trigger actually holds; machinery added for a trigger that does not hold is an Improvement to remove | SKILL.md Decisions that look ambiguous |

Procedure notes the rules do not cover:

- For an action delegating an intent-named operation (`complete`, `fail`,
  `expire`, `approve`), inspect the decision owner. The single call itself is
  allowed; pure policy must not be invented inline in the implementation.
- Inspect DTO fields recursively rather than trusting a wrapper named `domain`
  or `command`; delivery metadata (receipt handles, acknowledgements, topics,
  partitions, provider messages, raw requests) must not reach application,
  domain, or ports.
- For every Protocol, classify it: application I/O port, non-I/O Protocol with
  a trigger, or defect (callable stand-in for a domain function or an action,
  per-repository split, non-I/O Protocol without a trigger). A passing type checker does not
  prove a Protocol is useful.
- For each feature, record the entry point → SQL/external hop chain in the
  ownership matrix and name every hop that only forwards.
- For each action, compare its focused unit tests with its integration tests.
  Missing unit coverage is not itself a violation, but if business outcomes can
  only be shown through a real DB, broker, model, or SDK, check whether policy
  has escaped into that implementation.

### Behavioral probes

Static checks, lint, types, and happy-path tests do not find these. Run a probe
only when the service has the feature it names; a probe never justifies adding
machinery the brief does not need. Report a hit as a behavioral Violation when
it breaks a guarantee listed in [Classification](#classification), otherwise as
a risk with evidence.

| Feature | Probe |
|---|---|
| External HTTP/SDK integration | Map each concrete outcome (400/401/403/404/408/409/429/5xx, malformed 2xx) to a port result or error; a single `>= 400` branch is not a classification. Check a `409` on a *replay*, not only on the first call |
| Value sent outbound | Feed non-ASCII, control characters (including `NUL`), and length limits into every database column, URL, and header the value reaches; an identifier that becomes an `Idempotency-Key` header is the usual failure |
| Untrusted response headers | Check `Retry-After` and similar conversions for Unicode digits (`str.isdigit()` accepts them) and unbounded values that `int()` or `timedelta` rejects |
| PostgreSQL adapter | List the driver and dialect errors caught; check that timeout, cancellation, and failover wrapped in `DBAPIError` reach `Unavailable`. An unreachable-host test does not cover errors after connect |
| Leased outbox or broker batch | Compute the worst case from claim or receive to settlement for the *last* item of a full batch against the lease or visibility timeout and against the shutdown grace period. Check that the attempt counter counts attempts, not reservations, and that outcomes are counted or logged only after the fenced write succeeds |
| Consumer and sweeper on the same record | Compare their due and claim rules; the same record due in both at once should not produce two external calls unless the provider's idempotency is verified |
| Idempotency key | Replay after a policy change returns the original result; the same key with changed data gives a named conflict |
| Corrupt or poison rows | A cursor page of only corrupt rows followed by a valid row; a poison queue or outbox row ahead of a valid one; a schema-valid message the database rejects. None may stop the batch or crash-loop the process |
| Operator exit or unbounded retry | The discovery query, alert or threshold, and safe action live in the repository (not only in a build report or handoff) |
| Readiness | Test a stopped loop and a missing schema. `SELECT 1` proves only a connection; an exact migration-head check fails old replicas during a rolling deploy |

Summarize the semantic pass with a compact ownership matrix containing, as
applicable: action, business decision, boundary input, port, concrete
implementation, hop chain, state-transition owner, and lifecycle owner. Label
static-script findings separately from semantic findings.

## Library audit

For a member under `libs/` or `packages/`, read
`../python-service-architecture/references/shared-libraries.md` instead of the
service references, decide the library's one kind, and run library mode:

```bash
python scripts/audit_service.py libs/<lib>/src/<package> --library <contract|client|persistence|observability|genai|testing> --workspace path/to/repo [--service-package PACKAGE ...]
```

The workspace supplies the service packages (`services/*/src/*`) that the
independence contract must forbid, and the consumers checked for imports of
`_`-prefixed library names. The script checks the rules marked (checked) in
`shared-libraries.md`: service imports, environment and `pydantic_settings`
reads, logging configuration, imports the kind forbids, generic names,
`py.typed`, service shells, speculative packages, and the independence
contract. It does not run the service checks.

Then check semantically, each against `shared-libraries.md`:

- Which row of "Extraction triggers" justifies the library; a library no row
  justifies is an Improvement to inline back into its consumer.
- Does the code match one kind, or must it be split by kind?
- Every service importer is a layer the kind allows, and each service has the
  importer contract for it.
- The library translates every failure into its own errors, and each consumer
  translates those once into port errors.
- No resource the library was given is closed by it, and exactly one layer
  retries.

Classify, report, and route library findings like service findings.

## Shared-capability review

In a workspace, or a directory of sibling repositories passed as
`--workspace`, compare the reviewed service's technical plumbing with existing
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

- **Violation:** dependency direction, contract leakage, or ownership is wrong,
  or a behavioral guarantee the rules require is missing: a stuck intermediate
  state, a lost or duplicated external effect, an unguarded concurrent
  transition. Report behavioral Violations first; they cost the most in
  production.
- **Improvement:** a different shape materially improves isolation or
  navigation, including removing a speculative package or a non-I/O Protocol
  without a trigger. Forwarding layers and callable Protocols are Violations
  (see the hop-chain check).
- **Preference:** cosmetic difference without architectural consequence.

Do not present preferences as violations. Recommend removing layers as readily
as adding them; an audit that only ever adds structure is incomplete.

A service without the import-linter contract from `python-repository-setup`
("Architecture contracts") in pre-commit and CI has a Violation: agents write
this code, and rules that no tool checks drift. The bundled script is a
one-shot aid, not a substitute. Test placement for any additional fitness
tests: `testing.md`.

## Report and route

Report the static checks, the semantic findings with evidence and classification, the
ownership matrix, the shared-capability conclusions, and one recommended route:

- **No actionable findings:** state the checks run and the remaining
  uncertainty. Write no audit file.
- **Many findings:** coordinated changes across boundaries or consumers,
  shared-library extraction, state-transition or compatibility changes, or
  material design uncertainty. Count alone does not decide; one consequential
  finding can require this route. Invoke `openspec-propose` (fallback
  `../openspec-propose/SKILL.md`) to create the proposal, delta specs, design,
  and tasks, including evidence, classification, acceptance criteria,
  shared-capability conclusions, migration order, and verification tasks. If
  `openspec-propose` is not installed, write the audit file below instead.
- **Few findings:** fixes that are local, understood, and reversible. Write the
  audit file below.

The audit file is always the same: `PYTHON-AUDIT-<YYYY-MM-DD>.md` at the
reviewed repository root. If it exists, append a new section instead of
replacing it. For each finding record its classification, evidence, intended
fix, acceptance criteria, and verification steps as `- [ ]` checkboxes, with the
migration order when there is more than one. The audit's output is the report,
the proposal or audit file, and the skill-gap file.

## Skill-gap cross-validation

Run this only after the audit above is finished and its findings are
classified; it reads that list and never changes the report. Its question is
whether `python-service-architecture` is missing guidance the audit needed, not
whether the service is wrong.

For each finding, and for each place the audit had to guess, sort it:

- **Service breaks an existing rule:** an ordinary finding; not recorded here.
- **Rule exists but is ambiguous or contradicts another:** a gap.
- **No rule covers the situation:** a gap.

Before calling anything a gap, search every `python-service-architecture`
reference (`SKILL.md` and `references/*.md`) for the topic with several
phrasings; a rule found late is not a gap.

If at least one gap survives, write `SKILL-GAPS-<YYYY-MM-DD>.md` at the reviewed
repository root. If that file exists, append a new section instead of replacing
it. This file is independent of the route above: it records gaps in the skill, not
work on the service. Per gap, record: the code path and finding that exposed it, the rules searched
(file and section) and why they do not settle it, and the smallest guidance that
would have. Quote no more code than the evidence needs. If no gap survives,
create no file and say so in the report.

## Completion gate

Before declaring the audit complete, including one that verifies a structural
refactor:

1. rerun `scripts/audit_service.py`;
2. run the service's architecture-fitness tests;
3. run formatting, lint, type checking, and the relevant test profiles;
4. report remaining semantic risks that static checks cannot prove.

Never claim that the audit proves Protocol usefulness, error ownership, bootstrap
composition, or runtime behavior when only static imports were checked.
