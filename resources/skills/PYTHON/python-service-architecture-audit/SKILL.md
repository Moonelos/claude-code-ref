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

Third-party imports in `domain/`, `ports/`, and `application/` outside the
allowance in [boundaries.md, The core rule](../python-service-architecture/references/boundaries.md#the-core-rule)
are flagged. Pass `--allow-external` for a technology-neutral dependency the
repository deliberately admits (for example a shared contract library). The script also looks upward from the package for
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

Search imports and verify each check against its owner. (script) marks checks
the bundled script also runs statically; confirm its hits by reading the code.

| Check | Owner | Audit notes |
|---|---|---|
| `domain/` and `ports/` purity (script) | [boundaries.md, The core rule](../python-service-architecture/references/boundaries.md#the-core-rule) | |
| `application/` imports and no `opentelemetry` types (script) | [The core rule](../python-service-architecture/references/boundaries.md#the-core-rule); [`observability/`](../python-service-architecture/references/boundaries.md#observability) | |
| Import-linter contracts in pre-commit and CI | [`python-repository-setup` pre-commit.md, Architecture contracts](../python-repository-setup/references/pre-commit.md#architecture-contracts) | Missing contracts are a Violation. The script checks that the contracts' source and forbidden modules cover every required invariant, as `forbidden` or `layers` contracts, and that the `lint-imports` hook exists. Confirm CI runs it by reading `.github/workflows/`, `.gitlab-ci.yml`, `buildkite/`, or the documented pipeline; the script does not. A repository with no CI at all gets one Violation for the missing CI step, not one per contract. A migration runner with no application code gets no service contracts (the script skips it); check the runner contract instead |
| `api/` and `workers/` import no `config/`, `db/`, `adapters/`, or `genai/` (script) | [The core rule](../python-service-architecture/references/boundaries.md#the-core-rule) | |
| `db/`, `adapters/`, and `genai/` reach each other only through a port (script) | [The core rule](../python-service-architecture/references/boundaries.md#the-core-rule) | |
| Only the composition root imports `bootstrap/` (script) | [The core rule](../python-service-architecture/references/boundaries.md#the-core-rule) | |
| Who imports `Settings` and slice types | [`config/`](../python-service-architecture/references/boundaries.md#config) | |
| Every business entry point calls exactly one action and holds no business logic | [SKILL.md rule 2](../python-service-architecture/SKILL.md#core-rules-and-why); [Application ports](../python-service-architecture/references/boundaries.md#application-ports); [`application/`](../python-service-architecture/references/boundaries.md#application) | Entry points live in `api/`, `workers/`, `genai/` tools, or `main.py`, never in `bootstrap/` or `adapters/`. Technical endpoints and jobs are not findings ([api-and-workers.md](../python-service-architecture/references/api-and-workers.md#health-and-readiness)); nor is a read-only agent tool calling its task's collaborator ([ai.md](../python-service-architecture/references/ai.md#when-a-tool-calls-an-action)). For a one-call action, confirm it is a real public operation, not a step only a tool reaches (script flags tool-only actions) |
| Actions are grouped by resource and operation, with no ceremony around one-call actions | [SKILL.md, The feature shape](../python-service-architecture/SKILL.md#the-feature-shape); [SKILL.md rule 6](../python-service-architecture/SKILL.md#core-rules-and-why); [Tests of ports](../python-service-architecture/references/boundaries.md#when-a-port-earns-its-cost) | Semantic review only; the script does not check it. Judge whether the module split lets a reader find each operation, never how many calls a file holds |
| One port per I/O capability, implemented directly; never a Protocol for pure logic | [Application ports](../python-service-architecture/references/boundaries.md#application-ports); [persistence.md](../python-service-architecture/references/persistence.md#multiple-operations-in-a-uow) | Script flags ports without an implementation. A `__call__`-only Protocol standing in for a domain function or an action is a Violation (script) even when a test fakes it; the triggers apply only to other Protocols. A unit-of-work factory whose `__call__` returns a context manager is a port, not a stand-in |
| Non-port Protocols meet a trigger | [When a port earns its cost](../python-service-architecture/references/boundaries.md#when-a-port-earns-its-cost) | Script flags those with one implementation and no test reference |
| `db/` follows the package template: shared root modules, one capability per contract named after it, `store.py` in each capability subpackage, no imports between capabilities (script) | `python-sqlmodel-alembic` ([The db/ package](../python-sqlmodel-alembic/references/repo-layout.md#the-db-package)) | Script hits are REVIEW: confirm a capability without a matching `ports/` or `genai/` module implements no contract declared elsewhere before reporting it, and a root module outside the shared set has no capability to belong to |
| No root `messaging/` | [Adapters and their placement](../python-service-architecture/references/boundaries.md#adapters-and-their-placement) | |
| GenAI code lives under `genai/`; factories get resolved configuration; nothing built at import time | [ai.md, Factories and bootstrap wiring](../python-service-architecture/references/ai.md#factories-and-bootstrap-wiring) | |
| Model ids and tuning parameters come from settings; `init_chat_model` builds the SDK clients (script) | [ai.md, Ownership inside `genai/<task>/`](../python-service-architecture/references/ai.md#ownership-inside-genaitask) | Script flags literals and hand-built clients |
| No generic root or `core/` errors or constants (script) | [Errors and constants follow ownership](../python-service-architecture/references/boundaries.md#errors-and-constants-follow-ownership) | Script flags the generic filenames |
| Flat packages; provider identity alone is no folder (script) | [Flat-first growth across boundaries](../python-service-architecture/references/boundaries.md#flat-first-growth-across-boundaries) | Script flags one-module adapter subpackages |
| No deployable imports another deployable's private package | [shared-libraries.md](../python-service-architecture/references/shared-libraries.md#public-api-and-compatibility) | |
| No relative imports (script) | [SKILL.md rule 12](../python-service-architecture/SKILL.md#core-rules-and-why) | |
| Tests replace costly boundaries with small typed fakes, without patching SDK internals | [testing.md](../python-service-architecture/references/testing.md) | |

## Semantic audit

Trace real business actions from their process boundary through application
code, ports, concrete implementations, and bootstrap. For each trace, check the
owning rule:

| Check | Owner | Audit notes |
|---|---|---|
| **Hop chain** | [No forwarding layers](../python-service-architecture/references/boundaries.md#no-forwarding-layers) | Each boundary and extra collaborator owns an allowed responsibility; do not count calls as layers. Public one-call actions are allowed |
| **Logic outside actions** | [`application/`](../python-service-architecture/references/boundaries.md#application); [Thin routes](../python-service-architecture/references/api-and-workers.md#fastapi--http-api); [ai.md, Invocation and error translation](../python-service-architecture/references/ai.md#invocation-and-error-translation) | Look in routes, workers, the supervisor, and `genai/` for input resolution, cursor decoding, selection building, batch-continuation decisions, and business loops |
| **Preconditions** | [SKILL.md, Decisions that look ambiguous](../python-service-architecture/SKILL.md#decisions-that-look-ambiguous) | |
| **Port granularity** | [Application ports](../python-service-architecture/references/boundaries.md#application-ports) | A Protocol per repository or table is merged |
| **Mocks for pure logic** | [When a port earns its cost](../python-service-architecture/references/boundaries.md#when-a-port-earns-its-cost) (Tests of ports) | |
| **Port contract** | [Contract ownership](../python-service-architecture/references/boundaries.md#contract-ownership) | |
| **Error translation** | [errors.md, Translate once](../python-service-architecture/references/errors.md#translate-once); [Classification bases](../python-service-architecture/references/errors.md#classification-bases) | No central translator mapping unrelated owners; shared transient/permanent bases are allowed |
| **Port failure with no handler** | [errors.md, Handling boundaries](../python-service-architecture/references/errors.md#handling-boundaries) | |
| **Public error mapping** | [api-and-workers.md, Public error mapping](../python-service-architecture/references/api-and-workers.md#public-error-mapping) | Read the handler code, not only the registrations: a lookup keyed by `type(exc)` does not resolve along the MRO. Confirm a catch-all arm exists and logs status >= 500, and that the exhaustiveness test exists; a missing test is a Violation even when today's table happens to be complete |
| **Terminal failure records** | `python-logging` (fallback: `../python-logging/references/errors-and-security.md#failure-record-contract`) | At each process boundary (handler, worker, stream), check the level of the one terminal record per failure category: an unknown or internal failure logged below `error` hides defects from alerting |
| **Error, constant, validation, and helper owners** | [Errors and constants follow ownership](../python-service-architecture/references/boundaries.md#errors-and-constants-follow-ownership) | |
| **Repositories and adapters apply decisions** | [Repositories apply decisions](../python-service-architecture/references/boundaries.md#repositories-apply-decisions) | |
| **Supervisor and worker split** | [api-and-workers.md, Long-running worker](../python-service-architecture/references/api-and-workers.md#long-running-worker) | |
| **Consumers** | [SQS, Kafka, or another broker](../python-service-architecture/references/api-and-workers.md#sqs-kafka-or-another-broker) | |
| **Batches** | [errors.md, Handling boundaries](../python-service-architecture/references/errors.md#handling-boundaries) | |
| **Failure classification** | [errors.md, Classification bases](../python-service-architecture/references/errors.md#classification-bases); [persistence.md, Uncertain external writes](../python-service-architecture/references/persistence.md#uncertain-external-writes); [Validate external structure](../python-service-architecture/references/boundaries.md#validate-external-structure) | Credentials, missing endpoints, misconfiguration; a 2xx with an unreadable body; a corrupt stored row |
| **Inbound payloads** | [Validate external structure](../python-service-architecture/references/boundaries.md#validate-external-structure) | |
| **Constructor contracts** | [Constructor contracts](../python-service-architecture/references/boundaries.md#constructor-contracts) | |
| **GenAI task ownership** | [ai.md, Standard agent shape](../python-service-architecture/references/ai.md#standard-agent-shape); [Tools and MCP](../python-service-architecture/references/ai.md#tools-and-mcp) | |
| **Application telemetry** | [`observability/`](../python-service-architecture/references/boundaries.md#observability) | |
| **Pass-through wrappers** | [No forwarding layers](../python-service-architecture/references/boundaries.md#no-forwarding-layers) | Confirm each static forwarding candidate has no boundary or behavior of its own; distinguish public actions from extra helpers |
| **Atomicity** | [persistence.md](../python-service-architecture/references/persistence.md#choose-the-transaction-owner) (load only for relevant writes) | Name the transaction owner, concurrency guard, and DB/external-effect recovery contract, and each intermediate state's exit; verify with tests |
| **Package depth and flat-directory cohesion** | [Flat-first growth across boundaries](../python-service-architecture/references/boundaries.md#flat-first-growth-across-boundaries) | Inspect both unnecessary nesting and flat directories hiding capability clusters. Trace imports between implementations and supporting modules; name any cohesive group and the navigation benefit of colocating it. Report justified grouping as an Improvement, not a file-count Violation. This is semantic review; the static one-module adapter check does not cover it. |
| **Tool failures** | [ai.md, Tool rules](../python-service-architecture/references/ai.md#tool-rules) | |
| **Over-structure** | [SKILL.md, Where the hexagon applies](../python-service-architecture/SKILL.md#where-the-hexagon-applies); [When a port earns its cost](../python-service-architecture/references/boundaries.md#when-a-port-earns-its-cost); [ai.md, When a tool calls an action](../python-service-architecture/references/ai.md#when-a-tool-calls-an-action); [What a tool receives](../python-service-architecture/references/ai.md#what-a-tool-receives-and-how); [Technical jobs](../python-service-architecture/references/api-and-workers.md#technical-jobs) | Count the modules on each feature's path from entry point to SQL or external call. A read-only path over ~3 hops, or a feature spread over more than ~5 modules, is a candidate; name each hop and the trigger that justifies it. A count over the signal alone is an Improvement. Tool-only actions and the ports only they use, a `domain/` + port + action stack around a technical job, and process-lifetime collaborators in per-invocation context break must/never rules in their owners: Violations |
| **Port size** | [Application ports](../python-service-architecture/references/boundaries.md#application-ports) | More than ~12 methods, an implementation over ~400 lines, or a sibling `db/` module importing private helpers. A split must produce separately implemented ports; queries moved into module functions behind a class that wraps each in a transaction are a Pass-through finding |
| **Scope** | [SKILL.md, Decisions that look ambiguous](../python-service-architecture/SKILL.md#decisions-that-look-ambiguous); [`python-sqlmodel-alembic` work-queues.md, Choose the lightest coordination](../python-sqlmodel-alembic/references/work-queues.md#choose-the-lightest-coordination) | Behavioral machinery (intermediate states, sweepers, outboxes, idempotency keys, extra loops, leases, schedule tables) must be required by the brief or by a rule whose trigger holds; otherwise it is an Improvement to remove. Example: a lease row with owner, generation, and fencing around an idempotent retention purge, where an advisory lock suffices |

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
| Corrupt or poison rows | A cursor page of only corrupt rows followed by a valid row; a poison queue or outbox row ahead of a valid one; a schema-valid message the database rejects. None may stop the batch or crash-loop the process; a corrupt claimed row is not re-claimed forever, and one that is the user-visible status reaches the domain failure transition |
| Operator exit or unbounded retry | The discovery query, alert or threshold, and safe action live in the repository (not only in a build report or handoff) |
| Readiness | Test a stopped loop and a missing schema. `SELECT 1` proves only a connection; an exact migration-head check fails old replicas during a rolling deploy. In a hybrid process a crashed maintenance loop fails liveness, never readiness |

Summarize the semantic pass with a compact ownership matrix containing, as
applicable: action, business decision, boundary input, port, concrete
implementation, hop chain with its module count, state-transition owner, and
lifecycle owner. Label
static-script findings separately from semantic findings.

## Library audit

For a member under `libs/` or `packages/`, read
`../python-service-architecture/references/shared-libraries.md` instead of the
service references, decide the library's one kind, and run library mode:

```bash
python scripts/audit_service.py libs/<lib>/src/<package> --library <contract|client|persistence|configuration|observability|genai|testing> --workspace path/to/repo [--service-package PACKAGE ...]
```

The workspace supplies the service packages (`services/*/src/*`) that the
independence contract must forbid, and the consumers checked for imports of
`_`-prefixed library names. The script checks the rules marked (checked) in
`shared-libraries.md`: service imports, environment reads, kind-specific `pydantic_settings`
imports, logging configuration, imports the kind forbids, generic names,
`py.typed`, service shells, speculative packages, and the independence
contract. It does not run the service checks.

Then answer the [Review questions](../python-service-architecture/references/shared-libraries.md#review-questions)
semantically; rules marked **(review)** there have no static check.

For a database runtime, follow the scoped exception declaration and semantic
checks in `shared-libraries.md#database-runtime-exception`; run `--library
persistence`. The audit reports its exception as REVIEW, not general taxonomy
admission. Configuration and exception import placement are checked with
`--workspace`; importer contract coverage still needs semantic verification.

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
migration. See `shared-libraries.md#configuration-mechanics` for configuration ownership. Do not recommend generic shared dumping grounds or
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
  navigation and no must/never rule decides it: removing a speculative package
  or machinery whose trigger does not hold, or a hop or module count over a
  review signal.

A structure the owning reference forbids with must/never wording is a
Violation, not an Improvement: forwarding layers, callable Protocols standing
in for a function, non-I/O Protocols without a trigger, tool-only actions and
the ports only they use, and a `domain/` + port + action stack around a
technical job. Approximate numbers are review signals
([SKILL.md, Enforcement](../python-service-architecture/SKILL.md#enforcement)).
- **Preference:** cosmetic difference without architectural consequence.

Do not present preferences as violations. Recommend removing layers as readily
as adding them; an audit that only ever adds structure is incomplete. Report
over-structure findings in the same list as missing structure, with the same
evidence standard.

When the service's shape is one that `python-service-architecture` text
explicitly prescribes, it is not a finding against the service, even if it
looks wrong. Record it as a gap in `SKILL-GAPS-<date>.md`
([Skill-gap cross-validation](#skill-gap-cross-validation)), so the audit and
the architecture skill never contradict each other.

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
  finding can require this route. Invoke `$openspec-propose` (an external
  skill, not in this repository) to create the proposal, delta specs, design,
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
