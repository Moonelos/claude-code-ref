# Python skill guideline review

Scope: Python source and representative tests under `/Users/arafiet/MyProjects/Deep-Analyst/libs/` and `/Users/arafiet/MyProjects/Deep-Analyst/services/`, compared with the seven requested skills as they exist in this working tree. This is a proposal for **skill text**, not a list of required code changes. Existing working-tree edits to skills were left untouched. Priorities reflect the risk of agents repeating a pattern, not the severity of any cited line.

## Models, validation, and configuration

### 1. Make `Field` earn its place — **High**

**Target skill:** [python-settings-config/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-settings-config/SKILL.md:247) and [settings-py.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-settings-config/references/settings-py.md:60). Add the same short convention for ordinary Pydantic models to [python-service-architecture/boundaries.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md).

**Coverage assessment:** Partially covered, but current wording says to include descriptions on fields and to express defaults through `Field(default=...)`. That can train agents to wrap every field.

**Proposed rule:** Use `Field` when it adds a constraint, alias, serialization behavior, discriminator, `default_factory`, SQLModel mapping, or a description that explains non-obvious units, format, omission, or operational meaning. Otherwise use `name: Type` for required fields and `name: Type = value` for safe immutable defaults. In `BaseSettings`, retain `Field(alias=...)` where the exact environment variable differs from the Python field name. A field is required because it has no default; `Field(...)` is not required to make it required. Do not add descriptions that restate the field name.

**Why:** It makes contracts easier to scan without weakening validation or explicit environment mappings.

**Evidence:** [EntityDraft](/Users/arafiet/MyProjects/Deep-Analyst/libs/evidence_model/src/evidence_model/drafts.py:37) uses plain fields for ordinary data and `Field(min_length=1)` or a factory where behavior matters. [SSE event models](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/api/sse.py:52) do the same. [Settings aliases and bounds](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/config/settings.py:168) are a legitimate `Field` use. [SQLModel columns](/Users/arafiet/MyProjects/Deep-Analyst/libs/evidence_model/src/evidence_model/tables.py:36) are another exception.

**Good:** `status: TurnStatus`; `count: int = Field(ge=0)`; `port: int = Field(alias="APP_PORT", ge=1, le=65535)`.

**Bad:** `status: TurnStatus = Field(...)`; `enabled: bool = Field(default=True, description="Whether enabled.")` when no alias or other behavior is needed.

**Exceptions:** Public schema descriptions are useful when they add information for generated API docs. Keep explicit aliases when the deployment contract requires them.

### 2. Validate state transitions, not just initial model construction — **High**

**Target skill:** [python-service-architecture/boundaries.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md) under typed contracts; cross-reference from [pytest/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/pytest/SKILL.md) only for a regression that demonstrates the invariant.

**Coverage assessment:** Missing. The skills ask for typed and validated contracts but do not distinguish Pydantic validation at construction from unchecked `model_copy(update=...)`.

**Proposed rule:** Treat `model_copy(update=...)` as a trusted internal update: it does not revalidate the updated fields. Use it only when the replacement values are already validated and cannot violate a cross-field invariant. For untrusted input, arithmetic that may cross bounds, or an update that changes related fields, construct or `model_validate` a new model. Preserve immutable model transitions where they clarify state changes.

**Why:** A frozen model can still contain invalid state after an unchecked copy. A local check with the installed Pydantic version confirmed that `M(x=1).model_copy(update={"x": -1})` yields `-1` even when `x` has `Field(gt=0)`.

**Evidence:** [History transitions](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/domain/history.py:118) copy terminal statuses and message tuples after explicit checks; [usage accounting](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/domain/investigation_state.py:191) instead rebuilds with `model_validate` after arithmetic. [EntityDraft.with_refs](/Users/arafiet/MyProjects/Deep-Analyst/libs/evidence_model/src/evidence_model/drafts.py:74) illustrates a copy where callers must maintain the provenance invariant.

**Good:** `return UsageCounters.model_validate({**old.model_dump(), "rows": new_rows})` when `new_rows` may exceed a bound.

**Bad:** `return model.model_copy(update={"rows": untrusted_rows})` while assuming field validators ran.

**Exceptions:** Copying a known enum, boolean, or previously validated child can be simpler and safe; do not force full model reconstruction for every state flag.

### 3. Make configuration errors safe and actionable at the loading boundary — **High**

**Target skill:** [python-settings-config/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-settings-config/SKILL.md) and [settings-py.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-settings-config/references/settings-py.md).

**Coverage assessment:** Partially covered: secret masking is explicit, but the examples do not consistently require `ValidationError.errors(include_input=False)` or separate handling of missing versus malformed policy files.

**Proposed rule:** Translate Pydantic startup failures once, at the settings or secrets loader, into a typed startup error naming the source and field without echoing secret values or raw input. Use `errors(include_input=False)` for any error path that could include credentials or sensitive configuration. If a selected baseline is required, fail when it is missing; do not silently fall through to defaults. Keep source precedence and the allowlist visible at the settings boundary, and test the actual environment contract when multiple sources are merged.

**Why:** Safe errors help operators fix a deploy while preventing values from entering logs. Silent baseline absence can change policy unexpectedly.

**Evidence:** [Ingestion loader](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/config/settings.py:252) uses `exc.errors()`; [investigation loader](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/config/settings.py:289) and [secrets loader](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/config/secrets.py:152) use `include_input=False`. Both services use source allowlists, for example [ingestion policy fields](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/config/settings.py:67), which are worth standardizing. Their [settings contract tests](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/contract/config/test_settings.py) and [environment contract tests](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/contract/config/test_environment_contract.py) show the appropriate test boundary.

**Good:** `errors = exc.errors(include_input=False)` followed by field names and safe authored messages.

**Bad:** `raise SettingsError(str(exc))` for a model containing DSNs or tokens.

**Exceptions:** A deliberately optional local baseline may use code defaults, but that choice should be explicit and tested.

## Async execution and resource ownership

### 4. State the sync/async boundary explicitly — **High**

**Target skill:** [python-service-architecture/boundaries.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md) under adapters and bootstrap. The settings skill already covers `asyncio.to_thread` for sync secret SDKs; broaden that principle rather than repeating it there.

**Coverage assessment:** Partially covered for secret providers, missing for ordinary filesystem and synchronous SDK adapters called by async use cases.

**Proposed rule:** An `async def` should not make potentially slow synchronous file, SDK, database, or network calls on the event loop. Prefer a native async client when that boundary is truly concurrent. Otherwise isolate the blocking operation with a bounded `to_thread` call or put it in a synchronous stage outside the async hot path. Keep tiny predictable in-memory operations inline; do not wrap every `Path` call mechanically. Make cancellation and thread completion behavior explicit when the operation can outlive the request.

**Why:** Blocking calls can delay unrelated tasks and deadlines; indiscriminate thread offloading adds noise and can obscure resource ownership.

**Evidence:** [ingest_dataset](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/application/ingest_dataset.py:139) is async yet calls synchronous receipt reads/writes at [lines 166 and 187](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/application/ingest_dataset.py:166). The [S3 receipt adapter](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/adapters/s3/evidence_bucket.py:123) uses synchronous boto3, while [database stores](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/store.py:27) use async sessions. The mismatch is a reusable design question, not a request to change this implementation here.

**Good:** `receipt = await asyncio.to_thread(receipts.read, edition)` when the adapter may do remote I/O and concurrency matters.

**Bad:** Calling a remote synchronous SDK from many concurrent async tasks without accounting for event-loop blocking.

**Exceptions:** A one-shot CLI with no concurrent work may reasonably keep a synchronous stage, even if adjacent orchestration is async.

### 5. Pair broad cleanup catches with re-raise and bounded cleanup — **Medium**

**Target skill:** [python-service-architecture/boundaries.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md) and [otel-observability/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/otel-observability/SKILL.md) for telemetry-only exception isolation.

**Coverage assessment:** Partially covered through failure translation and telemetry error guidance; the distinction between cleanup and suppression is not concise enough.

**Proposed rule:** Catch `BaseException` only around cleanup that must also run on cancellation, then promptly re-raise; prefer `finally` or a context manager when possible. Catch `Exception` for a recoverable boundary only when the failure is translated, logged with bounded context, or deliberately converted to a documented degraded result. Never let best-effort telemetry replace the business outcome, but keep suppression local to the telemetry call rather than wrapping business logic. Bound cleanup that can hang.

**Why:** The same broad syntax is necessary in cleanup and dangerous in ordinary control flow. A clear rule prevents agents from copying it without its rationale.

**Evidence:** [Atomic receipt write](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/adapters/filesystem/receipt.py:30) uses `except BaseException` to remove a temp file and re-raise. [Ingestion failure ledger](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/application/ingest_dataset.py:159) records failure and re-raises. [Telemetry span wrapper](/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/spans.py:87) marks error and re-raises, while [provider shutdown](/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/providers.py:144) isolates exporter failures. [Readiness probes](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/pools.py:154) intentionally turn connection failures into a safe status.

**Good:** `except BaseException: cleanup(); raise` at a resource boundary.

**Bad:** `except BaseException: return None` in application logic.

**Exceptions:** A narrowly documented best-effort side channel, such as telemetry, may suppress its own errors.

## Persistence, contracts, and complexity

### 6. Make the database skill conditional on the actual persistence boundary — **High**

**Target skill:** [python-sqlmodel-alembic/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-sqlmodel-alembic/SKILL.md:77) and [repositories-and-queries.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md:29).

**Coverage assessment:** Existing rule is too broad. It says `repositories/` is the only place that imports `AsyncSession` and shows a port for every repository, while the architecture skill correctly says a fixed database often needs no extra Protocol.

**Proposed rewrite:** For a SQLModel/SQLAlchemy-backed service, keep session creation and transaction ownership in a narrow persistence boundary; keep queries in cohesive concrete repository or query adapters. Do not require the directory to be named `repositories/`, nor require an application port for each table or CRUD wrapper. Add a caller-owned port when it meaningfully isolates a business action from storage. Direct Psycopg is valid for PostgreSQL-specific privilege, cursor, or query-policy work; do not force it through SQLModel. Preserve parameterized SQL, bounded reads, explicit transactions, and least-privilege roles regardless of API.

**Why:** The current wording can push agents toward redundant layers and inappropriate ORM conversions.

**Evidence:** [SqlEvidenceStore](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/store.py:23) owns units of work and composes concrete repositories cleanly. [PostgresEvidenceReader](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/evidence_reader.py:46) and [database pools](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/pools.py:61) use direct Psycopg for specific read controls and role separation. The architecture skill's [port admission rule](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md:37) already cautions against automatic database ports.

**Good:** A concrete store with scoped transaction and one application-facing capability where it buys isolation.

**Bad:** One Protocol, implementation, and factory per table solely to conform to a template.

**Exceptions:** A SQLModel-specific task can continue to use the skill's detailed model and migration guidance.

### 7. Move SQL to files for readability and packaging, not query shape alone — **Medium**

**Target skill:** [python-sqlmodel-alembic/repositories-and-queries.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md:35).

**Coverage assessment:** Existing rule is overly rigid: a multi-table join or aggregate is treated as sufficient reason for a `.sql` file and it recommends import-time file I/O.

**Proposed rewrite:** Keep a query beside the adapter method while its parameters, result mapping, and SQL are easy to review together. Extract substantial static SQL to a packaged `.sql` resource when that makes review, reuse, formatting, or testing clearer. Load a packaged resource once through a deliberate resource helper or cache, and verify it ships in the wheel; avoid file reads at module import when they make imports fail due to packaging or working-layout assumptions. Parameterize values and strictly allowlist any dynamic identifiers or fragments.

**Why:** Query complexity and readability are related but not identical. Import-time I/O creates an avoidable packaging failure mode.

**Evidence:** [EvidenceReader](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/evidence_reader.py:62) keeps joins with the filter construction and row conversion. [Record query executor](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/record_query_executor.py:161) puts policy, execution bounds, and mapping together. The skill currently mandates an external file at [lines 43–45](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md:43) and reads it at import at [line 65](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md:65).

**Good:** A cohesive query method with bind parameters and a clear result mapper; a packaged SQL resource for a long report query.

**Bad:** A separate `.sql` file for every two-table join because of a fixed complexity trigger.

**Exceptions:** Migration SQL and large DBA-reviewed statements often warrant standalone files regardless of length.

### 8. Review the data path before adding indirection for size or reuse — **Medium**

**Target skill:** [python-service-architecture/modularization.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/modularization.md:21) and [python-service-architecture-audit/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture-audit/SKILL.md:45).

**Coverage assessment:** Partially covered: the skills correctly treat length as a review signal and reject speculative ports, but should say how to decide whether a long coordinator deserves extraction.

**Proposed rule:** For a long function, first trace its input, decision points, side effects, cleanup, and output. Extract a named helper or object only when it owns a separable decision, resource lifecycle, or reusable transformation; keep a readable coordinator intact when its steps form one use case. Prefer explicit typed values over reflective `getattr`, generic `object`, and `Any` when the set of shapes is closed and small. Do not add a layer merely to reduce line count or signature length.

**Why:** This gives agents a concrete review method without imposing arbitrary function or module limits.

**Evidence:** [SSE streaming](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/api/sse.py:116) is long because it owns event, cancellation, terminal outcome, and cleanup sequencing. [Bootstrap composition](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/bootstrap/runtime.py:215) has a similar orchestration role. In contrast, [projection conversion](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/repositories.py:69) uses `object`, `__slots__`, and a type ignore to save several explicit mappings, which makes the accepted shape harder to see.

**Good:** A coordinator whose named helpers correspond to distinct decisions or effects; explicit conversion functions for a few stable projection types.

**Bad:** A generic reflective mapper introduced only to remove a few lines of similar but meaningful mapping.

**Exceptions:** Reflection is reasonable in a generic framework adapter where supported input shapes are genuinely open-ended and validated at the edge.

## Tests and observability

### 9. Assert the contract once, with typed scenario setup — **Medium**

**Target skill:** [pytest/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/pytest/SKILL.md:168) and [core-principles.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/pytest/references/core-principles.md).

**Coverage assessment:** Partially covered: it already rejects incidental call order and overlarge fixtures, but the guidance could be more specific about multi-purpose tests and `Any`-typed fixture factories.

**Proposed rule:** In each test, keep assertions tied to the named regression and its dangerous partial effects. If a test verifies several independent contracts (business outcome, call counts, telemetry span order, payload shape), split it only where each piece has a distinct failure meaning and stable owner. Type reusable fixture factories or small fakes when their API is used repeatedly; use `Any` only for truly dynamic framework boundaries. Prefer one focused high-level wiring test plus narrow behavioral tests over repeating a full matrix at every layer.

**Why:** Failures become easier to diagnose, and typed setup exposes what a scenario actually controls. This is a refinement of the existing high-value-test rule, not a demand for one assertion per test.

**Evidence:** [Ingestion&#39;s first-run test](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/application/test_ingest_dataset.py:9) combines persistence, extraction counts, provenance, receipt, and detailed span assertions while typing shared fixtures as `Any`. Its [failure and idempotency tests](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/application/test_ingest_dataset.py:62) show clearer focused regression names. [Architecture contract tests](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/contract/architecture/test_import_boundaries.py:105) are a good use of narrow, explicit assertions over stable boundaries.

**Good:** `test_failure_leaves_no_receipt_and_marks_run_failed` with those two related outcome assertions.

**Bad:** Reasserting every internal collaborator count and exact telemetry ordering in every business use-case test.

**Exceptions:** A small end-to-end or contract test may need several related assertions to prove an atomic public outcome.

### 10. Keep observability policy out of business results, and scale signal detail with volume — **Medium**

**Target skill:** [otel-observability/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/otel-observability/SKILL.md:89) and [python-service-architecture/boundaries.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md:205).

**Coverage assessment:** Mostly covered. Improve the existing rule with a compact decision test, rather than add a parallel observability architecture rule.

**Proposed refinement:** Before adding a span, metric, callback, or log event, name the operational question it answers and the expected event volume. Instrument a stable boundary or meaningful business phase; avoid per-row/per-token signals unless sampled diagnostics justify them. The telemetry path may observe an outcome but must not choose or mutate that outcome. Keep failure isolation within telemetry methods, and have one clear owner for terminal failure logging.

**Why:** This prevents both telemetry noise and another layer of business-shaped callback plumbing.

**Evidence:** [Ingestion use case](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/application/ingest_dataset.py:139) records meaningful phases and aggregate candidate counts. [Attempt telemetry](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/observability/instrumentation/attempt.py:126) is substantial and its [safe-call boundary](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/observability/instrumentation/attempt.py:538) deliberately isolates failures. [Shared span wrapper](/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/spans.py:80) annotates and re-raises rather than deciding the business result.

**Good:** One run/phase span plus aggregate counts that answer a named operational question.

**Bad:** A span for every helper or row solely because the instrumentation API is available.

**Exceptions:** Short-lived diagnostic modes can add detail when volume and retention are bounded.

## Existing guidance that needs no duplicate rule

- **Boundary direction, port names, and library admission** are already explicit in [python-service-architecture](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/SKILL.md:77), its [boundaries reference](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md:37), and [python-repository-setup](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-repository-setup/SKILL.md:98). The [architecture contract tests](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/contract/architecture/test_import_boundaries.py:105) are good evidence of enforcement. Do not add another generic “use clean architecture” rule.
- **Explicit resource lifecycle and transaction scope** are already covered by the database and architecture skills and illustrated by [DatabasePools](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/pools.py:32) and [SqlEvidenceStore](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/store.py:27). Preserve this guidance while softening the SQLModel-only assumptions above.
- **Absolute imports, local constants/errors, and no generic `utils` package** are already covered in [boundaries.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md:260). There is no evidence-based need to repeat them in every skill.
- **Real integration boundaries and deterministic tests** are already covered in [pytest/SKILL.md](/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/pytest/SKILL.md:90) and exercised by [database privilege tests](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/integration/db/test_roles_and_tools.py:33). Do not turn them into a blanket requirement for integration tests on every adapter method.
- **Stable serialization and validation at external boundaries** already appear in [checkpoint state parsing](/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/domain/investigation_state.py:227), [S3 receipt parsing](/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/adapters/s3/evidence_bucket.py:123), and the architecture skill's typed-contract guidance. Recommendation 2 addresses the narrower gap: unchecked internal copies.
