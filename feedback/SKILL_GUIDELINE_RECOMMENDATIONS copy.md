# Recommendations for the Python development skills

## Scope and review basis

This is a read-only review of Python code in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/`, compared with the seven skills named in the request and their relevant references. The repository contains 298 Python files (including tests). I inventoried the tree, scanned recurring constructs and large functions, and read representative implementations, callers, tests, and skill text. The architecture audit script reported **zero static violations and zero review notices** for both `worker` and `orchestrator`; that result does not establish semantic correctness. These recommendations are about future agent guidance, not a request to change the cited code.

Paths below are absolute. Line references identify examples, not an exhaustive defect list. “Coverage” says whether the current skill already states the proposed rule.

## 1. Configuration and Pydantic

### 1.1 Use `Field` only when it adds a contract

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/SKILL.md` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/references/settings-py.md`.
- **Coverage / proposed edit:** **Partially covered, but contradictory.** Replace the blanket instructions to use `Field(...)` for every required value and `Field(default=...)` for every default, and to include a description on every settings field. State: **Use `Field` when it supplies a constraint, validation or serialization alias, `default_factory`, or useful metadata. A plain annotation makes a field required; a plain assignment gives it a default. Write a description when it explains units, format, source, an omission rule, or behavior that the name and type do not convey.** Apply the same principle to `BaseModel` and `BaseSettings`; SQLModel table fields are a separate case because `sa_column`, keys, and server defaults carry schema behavior.
- **Why:** Mechanical wrappers and descriptions hide meaningful constraints in noise. `Field(...)` is not necessary to make a Pydantic field required. The current scaffold encourages agents to repeat labels rather than document contracts.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/schemas/investigations.py:25-27` uses ordinary annotations for simple fields and `Field` for the constrained `max_exceptions`; the settings at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:154-182` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/config/settings.py:162-168` wrap nearly every field because of aliases/defaults. The skill mandates that style at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/SKILL.md:216-218` and `:247-248`.
- **Good:** `timeout_seconds: PositiveFloat = 30.0`; `report_limit: int = Field(default=20, gt=0, description="Maximum reports per request.")`; `bucket: str = Field(validation_alias="S3_BUCKET", min_length=1)` when that exact env contract is needed.
- **Bad:** `timeout_seconds: PositiveFloat = Field(default=30.0, description="Timeout seconds.")` when the description adds nothing.
- **Exceptions:** Keep `Field` for an established case-sensitive env alias, schema/JSON metadata, discriminators, computed defaults, and SQLModel mapping. Do not remove aliases as a style cleanup without checking `.env`, YAML precedence, and deployment contracts.
- **Priority:** **High**.

### 1.2 Keep cross-field validation pure and localize coherent checks

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/SKILL.md`.
- **Coverage / proposed edit:** **Partially covered.** The skill requires startup cross-field validation but says nothing about mutation or large validator bodies. Add: **An `after` validator should check invariants and return the model without changing fields. Express a derived value as a property or compute it before validation when it is truly input normalization. Group checks by one coherent policy when that makes failure messages easier to locate; do not split every condition into a helper merely to shorten a function.**
- **Why:** Mutation after validation can make `model_fields_set`, serialization, and subsequent validation disagree about whether a value came from a source or was derived. Long unrelated checks make policy ownership difficult to find.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:289-352` combines timing, Redis, admission, and AI budget checks in one validator and changes `min_inflight` at lines 291-292 based on `model_fields_set`.
- **Good:** `@property def effective_min_inflight(self) -> int: return min(self.min_inflight, self.initial_target)` if the effective value is derived; validate `min_inflight <= initial_target` separately if the input itself must be valid.
- **Bad:** `@model_validator(mode="after")` assigning to an input field and then using the mutated model as if it reflected the configured source.
- **Exceptions:** A documented `before` validator may normalize raw input when all input sources should receive the same normalization and the resulting field remains the canonical value.
- **Priority:** **High**.

### 1.3 Do not maintain a parallel settings registry without a consumer

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/SKILL.md`.
- **Coverage / proposed edit:** **Missing.** Add: **Avoid hand-maintained sets of setting names that repeat the model or configuration documents. Derive metadata from model fields or a schema when possible. Keep an explicit registry only when runtime behavior genuinely depends on it, and test that it stays in sync.**
- **Why:** A second list creates drift and makes a settings module much longer without strengthening the contract. The skill's existing document-contract tests should derive expected keys from the authoritative model/YAML, rather than invite another source of truth.
- **Evidence:** `YAML_POLICY_FIELDS` duplicates many fields in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:30-111` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/config/settings.py:28-54`; repository-wide source search found definitions but no consumers.
- **Good:** Compare parsed YAML keys with `Settings.model_fields` in the contract test, with a small explicit exclusion set for env-only inputs.
- **Bad:** An unused `frozenset` listing every YAML-backed setting beside a `Settings` class that already declares them.
- **Exceptions:** An explicit allowlist is justified when it controls a live security or source-precedence boundary and cannot reliably be derived from field metadata.
- **Priority:** **Medium**.

### 1.4 Test secret redaction at validation boundaries

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/SKILL.md` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/references/secrets-py.md`.
- **Coverage / proposed edit:** **Partially covered.** The skill already requires `SecretStr` and redaction, but should specify: **Exercise missing, malformed, and cross-field secret validation with a sentinel payload; assert the payload does not appear in the raised error, model representation, JSON rendering, or ordinary startup logs. Configure `hide_input_in_errors=True` where it contributes to this contract.**
- **Why:** Masked `SecretStr` rendering alone does not prove that validation and startup exceptions are safe. This is a consistency check, not a mandate to add duplicate tests for every credential.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/config/secrets.py:13-25` uses `hide_input_in_errors=True`, while `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/secrets.py:13-25` does not. The orchestrator test at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/config/test_settings.py:141-147` checks JSON redaction, a useful pattern to extend to the actual failure paths.
- **Exceptions:** Provider SDK errors may need separate sanitization at their adapter boundary; a Pydantic setting cannot control those messages.
- **Priority:** **Medium**.

## 2. Async work, errors, and resource ownership

### 2.1 Make sibling task lifetime explicit

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/api-and-workers.md`.
- **Coverage / proposed edit:** **Partially covered.** The skill assigns long-running tasks to supervisors, but lacks a task-lifetime rule. Add: **When one operation starts sibling tasks, keep them in a lexical scope and define what happens if any fails, is cancelled, or finishes first. Prefer `asyncio.TaskGroup` for fail-together tasks when supported. Use explicit `create_task`/`wait` when first-completed semantics are required, but cancel and await every remaining task in `finally`; preserve the original failure.**
- **Why:** Manually paired `create_task` and `gather` is easy to get subtly wrong under cancellation. The point is structured lifetime, not blindly replacing specialized race logic with `TaskGroup`.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/resolve_control_context.py:135-178` starts two groups of tasks and has a separate cancellation helper at `:236-240`; `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:215-236` correctly cancels and awaits action/heartbeat peers for first-completed behavior. The latter is a good exception to standardize.
- **Good:** `async with asyncio.TaskGroup() as group: left = group.create_task(fetch_left()); right = group.create_task(fetch_right())` for independent fetches whose failures should terminate the group.
- **Bad:** Starting tasks, awaiting only one, and returning while a sibling still runs.
- **Exceptions:** Supervisors own process-wide tasks; a first-completed heartbeat race needs explicit result handling and cleanup. Use the repository's supported Python version before selecting `TaskGroup`.
- **Priority:** **High**.

### 2.2 Distinguish a recoverable boundary from an internal failure

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/boundaries.md` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/otel-observability/references/conventions/errors.md`.
- **Coverage / proposed edit:** **Partially covered.** Port-owned error translation and structured failure logging are covered. Add: **Catch a broad `Exception` only at an explicit process boundary that can classify an unexpected failure and make a safe retry/acknowledgment decision. Inside adapters and actions, catch the known SDK, parsing, timeout, and domain failures that have different handling. Log an unexpected exception once at the boundary that owns the final outcome, with stable operation, outcome, and error type; lower layers should raise with context rather than log and re-raise by default.**
- **Why:** Broad catches are sometimes essential in workers, but scattered catches make it hard to distinguish expected retries from defects and can duplicate telemetry. The rule must preserve cancellation propagation.
- **Evidence:** The worker message boundary classifies unexpected failures at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:136-180`, then records a delivery decision at `:263-297`. Narrow provider exception translation is visible at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/candidates.py:64-76`. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/supervisor.py:21-44` shows a clear loop-level recovery boundary.
- **Good:** `except (OSError, SQLAlchemyError) as exc: raise SourceUnavailable(...) from exc` inside a DB adapter, with the supervisor logging its final retry decision.
- **Bad:** `except Exception: logger.exception(...); raise` in each layer of the same call path.
- **Exceptions:** Log at a lower layer when it contains unique diagnostic facts that cannot cross the port contract safely. A cleanup handler may catch `BaseException` solely to release resources and immediately re-raise; do not turn cancellation into an ordinary retry.
- **Priority:** **Medium**.

### 2.3 Clarify readability limits for composition and protocol code

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/modularization.md`.
- **Coverage / proposed edit:** **Partially covered.** The reference treats line count as a review signal. Add: **A long bootstrap composition function may remain one visible wiring map if it makes dependency construction and lifetime easier to follow. Split only at stable resource or capability seams, and return typed bundles when they represent those seams; do not introduce a factory per constructor or a generic registry to satisfy a line target. Conversely, split a shorter function if unrelated policy and effects are interleaved.**
- **Why:** Mechanical function-length rules can fragment the dependency graph and make navigation worse. This makes the existing exception actionable.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:219-438` is long mostly because it exposes wiring; `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/client.py:84-185` is also long but contains retry, authentication replay, response closure, and result policy that deserve a different responsibility review.
- **Exceptions:** Split bootstrap wiring when resource acquisition/cleanup, independent features, or tests already have distinct ownership. Do not preserve a giant composition block solely to keep everything in one file.
- **Priority:** **Medium**.

## 3. Database work and efficient reads

### 3.1 Replace the absolute repository-location rule with an ownership rule

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-sqlmodel-alembic/SKILL.md` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md`.
- **Coverage / proposed edit:** **Existing rule is too broad.** Rewrite “`repositories/` is the only code that imports `AsyncSession`, `text()`, or a model class for querying” as: **Keep SQL inside the database adapter owned by the capability. Place ordinary entity reads/writes in repositories. A cohesive operation using a connection, transaction, advisory lock, schema probe, retention pass, or external database library may live in a precisely named `db/` module or library capability. Application/domain/ports never run SQL.** Rewrite the diagram's `repositories/ → queries/*.sql` as an optional shape, not an invariant.
- **Why:** The current wording would force transactional retention and external CTC readers into misleading repository names, or push unrelated code through a repository merely to satisfy a folder rule.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/retention.py:20-100` owns a transaction and advisory lock for one retention pass; `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/candidates.py:21-82` owns a bounded read-only external database capability. These are cohesive database adapters outside `repositories/`. The overly strict rule is at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-sqlmodel-alembic/SKILL.md:89-99`.
- **Good:** `db/repositories/investigations.py` for entity lookup; `db/retention.py` for one transactional maintenance pass.
- **Bad:** Moving advisory-lock code into an unrelated entity repository solely because it calls `connection.execute()`.
- **Exceptions:** If a single repository owns the full operation and the name remains accurate, keep it there; avoid proliferating one-file wrappers.
- **Priority:** **High**.

### 3.2 Select the fields an operation needs, especially for wide rows

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md`.
- **Coverage / proposed edit:** **Missing.** Add: **For list/status/batch queries over a table with large JSON or text columns, inspect the return contract and select only required columns. Use full models when the operation needs them or when a narrow projection would add more complexity than it saves. Apply a DB-side page/batch bound before converting rows or building response objects.**
- **Why:** Fetching large report/analysis columns for status or ID lookup spends database I/O and memory without helping readability; simple projections can clarify the repository's output contract.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/repositories/investigations.py:123-164` selects full `Investigation` rows for status-style records; the model includes report and analysis payload columns at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_db/src/platform_db/models/investigation.py:115-125`. The CTC candidate reader shows the good bounded, narrow pattern at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/candidates.py:28-62`.
- **Good:** `select(table.c.id, table.c.status, table.c.attempt_count).where(...).limit(page_size)` for a status page.
- **Bad:** `select(Investigation)` for a batch whose output uses only ID and status while every row may contain a full report.
- **Exceptions:** A detail/report operation that returns the report legitimately loads it. Avoid projections for tiny, bounded models without material payload cost.
- **Priority:** **Medium**.

### 3.3 State the dynamic SQL boundary precisely

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md`.
- **Coverage / proposed edit:** **Missing.** Add: **Bind data values as query parameters. Identifiers cannot be bound as values: when schema/table names must be dynamic, validate them against a narrow identifier rule or trusted allowlist, then quote with the dialect's identifier mechanism. Keep this logic at one database adapter boundary. Avoid hand-escaped value lists when parameter binding is available.**
- **Why:** The distinction is easy to miss in templated SQL and makes query safety reviewable without banning necessary dynamic schemas.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/exceptions.py:160-163` validates and quotes dynamic identifiers, and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/candidates.py:39-60` binds values. By contrast, `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/ctc/query_executor.py:67-78` manually escapes and interpolates a value list into a query.
- **Good:** Validate `schema` as an identifier, quote it, and pass `exception_name` and `limit` as `:exception_name`/`:limit` parameters.
- **Bad:** Interpolating caller-provided values directly into a SQL string, even when each call site currently supplies trusted strings.
- **Exceptions:** Agent-generated SQL is a separate deliberately constrained execution boundary; it still needs read-only validation, row limits, timeouts, and the existing dedicated tests.
- **Priority:** **High**.

## 4. Contracts, typing, and tests

### 4.1 Choose validation machinery by boundary, not by fashion

- **Target skill:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/boundaries.md`.
- **Coverage / proposed edit:** **Partially covered.** The skill requires typed contracts and boundary validation, but does not say when a dataclass or Pydantic model is appropriate. Add: **Use ordinary typed dataclasses or small immutable value objects for trusted in-process domain data. Use Pydantic at untrusted input, settings, and wire/schema boundaries when coercion, validation, or schema generation is useful. Decode and normalize legacy formats once at the boundary; pass a stable typed value inward. Do not add Pydantic to every internal result solely for consistency.**
- **Why:** This keeps validation explicit without paying runtime/model complexity at every internal hop or duplicating decoding across consumers.
- **Evidence:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/investigation_contracts/src/investigation_contracts/events.py:15-64` uses a frozen dataclass plus one decoder for a versioned event; `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/investigation_contracts/src/investigation_contracts/analysis.py:13-84` does likewise for persisted analysis; `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/schemas/investigations.py:11-40` appropriately uses Pydantic for external HTTP input.
- **Good:** `decode_event(raw) -> InvestigationRequested` at the broker boundary, then pass the typed event to application code.
- **Bad:** Passing raw `dict[str, Any]` through the application and revalidating different subsets in several actions.
- **Exceptions:** Pydantic is suitable for an internal type when its validation/serialization is itself part of a real contract; dataclasses still need explicit checks when callers can construct invalid instances.
- **Priority:** **Medium**.

### 4.2 Preserve the existing test guidance; add no duplicate rule

The `pytest` skill already tells agents to assert behavior and failure modes, keep external tests controlled, avoid arbitrary sleeps and mock-only assertions, and prove test sensitivity where practical (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/pytest/SKILL.md:16-42` and `:160-207`). Those rules fit the focused fake-based supervisor tests at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/bootstrap/test_supervisor.py:42-89`, the real database concurrency tests at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/integration/db/test_investigation_repositories.py:150-185`, and the versioned wire fixtures under `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/investigation_contracts/tests/fixtures/`. I recommend keeping that guidance as written rather than adding another generic “write good tests” rule.

## Existing guidance that should remain canonical

The following good practices are already stated sufficiently and should **not** be duplicated in another skill:

- Dependency direction, capability-owned ports, flat-first packages, and avoiding speculative shared libraries: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/SKILL.md:69-111` and its `references/boundaries.md`. The code's application/port/adapter arrangement provides concrete examples in both services.
- Side-effect lifecycle in bootstrap and per-operation DB sessions: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/api-and-workers.md` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-sqlmodel-alembic/references/engine-and-session.md`. The worker and orchestrator runtimes own clients and cleanup.
- Typed, non-secret settings, separate `SecretStr` secrets, explicit source precedence, and startup validation: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/SKILL.md:205-274`. The proposed changes above refine style and verification; they do not replace this contract.
- Bounded telemetry cardinality, content-gated GenAI capture, and one instrumentation owner per boundary: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/otel-observability/SKILL.md:60-92`. The content limiter at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/genai_content.py:121-151` is a useful code example. No new telemetry rule is needed for that behavior.
- Meaningful comments over narration and line counts as review signals: the repository `AGENTS.md` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/modularization.md:17-37`. The comment explaining a `READ COMMITTED` race at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/repositories/investigations.py:108-110` is an example to retain.

## Suggested edit order

1. Fix the conflicting `Field` wording and scaffolds in `python-settings-config`.
2. Relax the repository-location invariant in `python-sqlmodel-alembic`; then add query projection and dynamic SQL guidance there.
3. Add validator purity, async task lifetime, and boundary error guidance to their owning skills.
4. Add the smaller consistency rules for settings registries, redaction tests, composition, and contract types.

No production code, tests, or skill source files were changed by this review.
