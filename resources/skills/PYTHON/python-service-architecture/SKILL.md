---
name: python-service-architecture
description: >-
  Design, scaffold, refactor, or review modules and tests inside a Python backend
  service or internal library. Use for application/domain/port boundaries,
  adapters, bootstrap, APIs, workers, GenAI code, persistence ownership, and test
  profiles. Use `python-repository-setup` for top-level workspace and tooling
  decisions, and domain-specific skills for implementation mechanics.
---

# Python Service Architecture

Enforce the canonical structure below across Python backend deployables. Use the
lighter shared-library structure for non-deployable packages; never copy a
service shell into a library. Ownership and dependency direction take priority
over cosmetic symmetry.

## Required discovery

Before proposing or changing a structure:

1. Inspect the actual package tree, entry points, imports, tests, and deployment
   process. For tests, inspect collection configuration, markers, fixture scope,
   support-module imports, external-resource requirements, pre-commit/pre-push
   scopes, and CI selection. Do not infer architecture or test type from
   filenames alone.
2. Classify the member as an independently deployable service or a
   non-deployable internal library; do not infer that from its current folder.
3. For a service, identify meaningful business actions, outcomes, and process
   types. For a library, identify its public capability, current consumers, and
   compatibility contract.
4. Identify external effects and lifecycle resources owned by the member:
   database, HTTP clients, storage, queues, browser, files, LLMs, telemetry, and
   clocks. A library should own only effects intrinsic to its published capability.
5. Trace current dependency direction and locate service-private imports,
   concrete external implementations, and consumer reach-through into private
   library modules.
6. Preserve repository conventions unless changing them provides a clear,
   stated benefit. Never reorganize unrelated services merely for symmetry.
7. Before adding or copying technical plumbing, inspect existing libraries and
   matching implementations in other members, comparing meaning, lifecycle,
   inputs, and dependencies. Prefer an existing compatible public library API
   over another copy. Duplicates are resolved by the triggers in
   [shared-libraries.md](references/shared-libraries.md#extraction-triggers).

## Reference routing

For a deployable service, read:

- [references/templates.md](references/templates.md) for the canonical tree and
  placement map;
- [references/boundaries.md](references/boundaries.md) for dependency,
  ownership, ports, bootstrap, constants, and package-growth rules;
- [references/errors.md](references/errors.md) for raising, translating,
  classifying, handling, and exposing failures;
- [references/testing.md](references/testing.md) for test placement, profiles,
  markers, CI selection, and support packages.

For an internal library, read
[references/shared-libraries.md](references/shared-libraries.md) and
[references/testing.md](references/testing.md) instead; the library reference is
authoritative wherever service rules would imply extra folders. Load only the
additional references that apply:

- Read [references/async-and-lifecycle.md](references/async-and-lifecycle.md)
  for any service with async I/O or long-lived resources.
- Read [references/api-and-workers.md](references/api-and-workers.md) for an HTTP
  API, worker, scheduled process, queue/Kafka/SQS consumer, or hybrid service.
- Read [references/ai.md](references/ai.md) when the package invokes an LLM,
  builds an agent or graph, exposes AI tools, or has prompts/model middleware.
- Read [references/modularization.md](references/modularization.md) when splitting
  existing modules, migrating an established service, or reviewing structure
  that has grown unclear.
- Read [references/shared-libraries.md](references/shared-libraries.md) when
  discovery finds a shared-capability candidate, even during a service task.
  Keep it loaded when extracting service code into `libs/*` or reorganizing an
  existing library.

Below module placement, language-level idioms and size signals are owned by
`python-code-conventions` (fallback: `../python-code-conventions/SKILL.md`).
General code-style rules come from CLAUDE.md.

## Enforced invariants

These are requirements, not optional examples:

1. **Business execution lives in `application/`.** Use it for executable
   business-value actions, use cases, and orchestration. Business capabilities
   are organized inside `application/` and `domain/`; there are no root-level
   peers of the technical boundaries (`pipeline/`, `use_cases/`, `workflows/`,
   `operations/`). A true transport-only or health-only process is an explicit
   exception that must be explained.
2. **Dependencies point inward.** Application code never imports `bootstrap`,
   `api`, consumers, `adapters`, `db`, or `genai`; domain and ports never know
   framework or SDK details. `bootstrap/` is the ordinary runtime composition
   root. See `boundaries.md` for the complete dependency and contract rules.
3. **Concrete integrations have stable owners.** HTTP belongs in `api/`,
   persistence in `db/`, and all other non-GenAI integrations in root
   `adapters/`, flat until the promotion rule in `boundaries.md` justifies a
   provider subpackage. There is no root `messaging/`.
4. **Every GenAI implementation concern lives in root `genai/`; telemetry stays
   in root `observability/` or a justified observability library.** LLMs, agents,
   prompts, AI schemas, tools, graphs, model bindings, and behavior-changing AI
   middleware belong in `genai/`.
   Telemetry-only callbacks, tracing middleware, usage adapters, and agent-span
   wrappers belong in the service's existing `observability/` boundary by
   default, even when they import LangChain or another framework. Application
   code sees a typed port and business result. Models are built by factory
   functions that `bootstrap/` calls with the task's settings slice; there is no
   mandatory `llm.py`. The application-facing implementation is named after its
   port capability. Read `ai.md` for the ownership rules.
5. **Package growth is flat-first.** Start with the fewest cohesive modules and
   introduce only the narrower subpackage whose independent ownership, change,
   setup, or naming pressure justifies it (`boundaries.md`).
6. **Names, errors, constants, and contracts follow ownership.** Ports describe
   caller-needed external capabilities, not implementations or deterministic
   in-process logic. Never create root `constants.py` or root/`core`/`common`
   error collections. Translate concrete failures to the port-owned contract
   before application code sees them; error design is in `errors.md`.
7. **Tests belong to their member and actual execution profile.** Keep them
   beside the member's `src/`. When multiple profiles exist, classify them as
   `unit`, `integration`, `contract`, or `e2e` by what they execute, then by
   behavioral owner (`testing.md`). Test design is owned by `pytest`.
8. **Internal libraries use the library shape.** They do not acquire a service
   shell for symmetry, import deployable-private code, or become generic shared
   dumping grounds. Promote code only after real reuse or a concrete independent
   compatibility boundary exists.
9. **All Python imports are absolute** (enforced by Ruff `TID252`).
10. **`src/<package>/config/` holds Python settings code, not YAML baselines.**
   YAML location and merge order are owned by `python-settings-config`
   (fallback: `../python-settings-config/SKILL.md`).

Create only directories required by the current member. The canonical tree is
a placement policy, not permission to add empty packages.

## Output and implementation behavior

For a design or review, provide:

1. How the canonical shape applies and any explicit, justified exception.
2. A target source and test tree containing only relevant directories.
3. A short dependency map and ownership notes for ambiguous source and test
   files, including each test's execution profile when it is not obvious.
4. Current violations, fixture/CI migration risks, and the smallest coherent
   migration sequence.

For implementation, state how the service or library shape applies before broad
file movement. Move one coherent boundary, business action, library capability,
or test profile at a time; update imports, entry points, consumers, fixture
scope, markers, pre-commit paths/filters, and CI selectors; and run focused tests
after each meaningful slice. Preserve behavior during a structure-only refactor;
do not mix business redesign into file movement unless the user explicitly
requests both.

## Related skills

- Use `python-repository-setup` to decide whether shared code earns a
  workspace member and for `pyproject.toml`, dependency isolation, lockfiles,
  scoped installs, root pre-commit/pre-push tooling, and Docker build layout.
- Use `python-code-conventions` for language-level idioms and size signals.
- Use `python-settings-config` for detailed settings/secrets implementation.
- Use `python-sqlmodel-alembic` for SQLModel, repositories, sessions, units of
  work, work queues, and Alembic structure.
- Use `otel-observability` for OpenTelemetry tracing, metrics, and shared
  observability libraries; `python-logging` for application logging, including
  exception detail.
- Use `pytest` for test design and `python-service-architecture-audit` for the
  audit procedure.
