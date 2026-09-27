# Skill guideline review: `libs/` and `services/`

This is a recommendation document, not a proposed application refactor. I inspected the Python source and representative tests across the six libraries and three deployables, then compared candidate rules with the seven named skills and their relevant references. The bundled architecture static checks reported **zero violations** for each service; the orchestrator had three review notices about `offset` fields. Those notices are not treated as findings here. Priorities describe the value of changing the skill text, not the urgency of editing the cited code.

## Configuration, Pydantic, and validation

### 1. Make `Field(...)` earn its place

- **Target skill:** [python-settings-config](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-settings-config/references/settings-py.md) (including its scaffolds); add a cross-reference in [python-sqlmodel-alembic](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-sqlmodel-alembic/references/models-and-base.md) for table models.
- **Coverage:** **Partially covered, but the current text conflicts with this rule.** The settings reference requires `description=` on fields and presents `Field(...)` as the way to mark a required value. Its examples wrap ordinary defaults. It already gives good guidance on aliases and constrained types.
- **Proposed rule/guideline:** Use `Field(...)` when it adds a constraint, alias or validation alias, `default_factory`, schema metadata that explains a non-obvious contract, or SQLModel column behavior. A required Pydantic field can be a bare annotation; an ordinary default can be a normal assignment. Keep explicit aliases where they are part of the environment contract. Descriptions should explain units, accepted format, ownership, omission behavior, or another fact that cannot be inferred from the name and type. Rewrite the scaffold and remove the blanket “Include concise `description=` text on fields” instruction; do not mechanically remove aliases or SQLModel `sa_column` declarations.
- **Why it should be added:** Mechanical `Field` calls make large settings models longer and can create documentation that merely repeats the field name. The useful descriptions become harder to spot.
- **Evidence/pattern observed:** Both service settings modules contain descriptions such as `"Im base url."` and `"Db pool size."` beside descriptions that carry actual meaning, such as the scope and non-transmission of `im_source_scope`: [worker settings](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/config/settings.py:22), [worker settings](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/config/settings.py:34), [orchestrator settings](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/orchestrator/src/orchestrator/config/settings.py:59). The existing instruction is in [settings-py.md](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-settings-config/references/settings-py.md:74). SQLModel declarations use `Field` meaningfully for column mappings: [investigation model](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/platform_db/src/platform_db/models/investigations.py).
- **Good example:** `im_source_scope: str = Field(alias="IM_SOURCE_SCOPE", description="Scopes rate limiting and deduplication; never sent to IM.")`; for a model with no env alias requirement, `max_rows: PositiveInt = 1000`.
- **Bad example:** `max_rows: PositiveInt = Field(default=1000, description="Max rows.")` solely to fill out a template.
- **Exceptions / when the rule should not apply:** Preserve explicit aliases when case sensitivity or backward compatibility requires them. SQLModel table fields commonly require `Field` for primary keys, foreign keys, defaults, indexes, and SQLAlchemy columns.
- **Priority:** **High**.

### 2. Keep settings validators declarative and construct derived policy once

- **Target skill:** [python-settings-config](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-settings-config/references/settings-py.md).
- **Coverage:** **Partial.** The skill asks for cross-field validation at startup but does not distinguish validation from normalization or describe where a derived business policy object should be built.
- **Proposed rule/guideline:** An `after` validator should normally check invariants and return the model without mutating it, especially when the model is frozen. If one setting is derived from others, compute it in a named property or construct a typed policy once at bootstrap; validate that resulting policy there. Avoid building the same many-field policy once for validation and again for use. Use a `before` validator only when input normalization is genuinely part of the settings contract and its source precedence is clear.
- **Why it should be added:** Mutation through `object.__setattr__` defeats the expectation created by `frozen=True`; constructing a policy twice creates two long mappings that can drift when fields are added.
- **Evidence/pattern observed:** [worker settings](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/config/settings.py:238) derives `admission_min_inflight` by bypassing freezing and constructs `AdmissionProfile` only to validate it. [Worker bootstrap](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/bootstrap/supervisor.py:52) constructs that profile again with the same long field list. [AdmissionProfile](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/domain/admission.py:14) already owns the cross-field invariants.
- **Good example:** `profile = admission_profile_from_settings(settings)` once in bootstrap, with the helper beside the bootstrap composition code and `AdmissionProfile.__post_init__` validating its own invariants.
- **Bad example:** `object.__setattr__(self, "admission_min_inflight", minimum)` inside a frozen settings model, then repeating a long constructor elsewhere.
- **Exceptions / when the rule should not apply:** A small model-level validator that checks a few settings directly is appropriate. A derived field can live on a model when it is part of its public schema and uses a supported, explicit validation mechanism.
- **Priority:** **Medium**.

## Persistence and repository boundaries

### 3. Clarify that transaction coordinators may own sessions

- **Target skill:** [python-sqlmodel-alembic](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-sqlmodel-alembic/SKILL.md) and [repositories-and-queries.md](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md).
- **Coverage:** **Conflicting wording.** The skill says only `repositories/` imports `AsyncSession` or model classes for querying, while its session reference allows a unit-of-work owner. The repository follows a useful two-layer pattern that the strict wording appears to prohibit.
- **Proposed rule/guideline:** Keep SQL statements and table-model querying in repositories. A thin `db/*_transactions.py` or unit-of-work coordinator may import `AsyncSession` and the session factory to define transaction scope, invoke one or more repositories atomically, and translate database failures into the application-facing contract. It should not implement queries or business policy. Do not require a coordinator for a single trivial call when an existing boundary already owns the session.
- **Why it should be added:** The skill should preserve transaction ownership without forcing commit logic into repository methods or every operation into bootstrap.
- **Evidence/pattern observed:** [worker transaction coordinator](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/db/transactions.py:32) and [orchestrator discovery coordinator](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/orchestrator/src/orchestrator/db/discovery_transactions.py:18) use `sessions.begin()` and call concrete repositories; the repositories hold SQL. The overly strict text appears in the [DB skill](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-sqlmodel-alembic/SKILL.md:88).
- **Good example:** `async with sessions.begin() as session: return await WorkRepository(session).claim(...)`.
- **Bad example:** A transaction coordinator that also embeds `select(...)`, row projections, and retry policy.
- **Exceptions / when the rule should not apply:** Migration code, readiness checks, and narrowly owned setup code may need direct database access; name these exceptions explicitly rather than implying that everything belongs in `repositories/`.
- **Priority:** **High**.

### 4. Choose external SQL by readability and query ownership, not join count

- **Target skill:** [python-sqlmodel-alembic](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md) and the corresponding [core convention](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-sqlmodel-alembic/SKILL.md).
- **Coverage:** **Overly broad existing rule.** The reference says a multi-table join or aggregate moves to `.sql` even if the expression is short and clear.
- **Proposed rule/guideline:** Keep short, typed SQLModel/SQLAlchemy expressions inline when the filter, joins, projections, and bound parameters are readable together. Move a query to a `.sql` resource when the SQL itself is substantial, uses database-specific constructs that read better as SQL, or benefits from independent review and testing. Keep SQL parameterized and load resources once. Do not move a query solely because it contains one join or aggregate.
- **Why it should be added:** Unnecessary SQL files make readers jump between files and can discard useful model-aware typing. Conversely, reporting SQL may be much clearer as SQL.
- **Evidence/pattern observed:** [orchestrator query repository](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/orchestrator/src/orchestrator/db/repositories/queries.py:115) has a readable join inline; [worker work repository](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/db/repositories/work.py:48) uses a concise aggregate expression inline. A separate [report query](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/orchestrator/src/orchestrator/db/queries/request_totals.sql) shows where a resource is useful. The present threshold is in [repositories-and-queries.md](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-sqlmodel-alembic/references/repositories-and-queries.md:43).
- **Good example:** The short `select(Investigation).join(RequestInvestigation).where(...)` stays beside its projection.
- **Bad example:** A new `.sql` file for a one-join lookup only to satisfy a join-count rule.
- **Exceptions / when the rule should not apply:** Database-specific reporting, CTE-heavy statements, or SQL whose formatting is awkward in Python may warrant a `.sql` file even with few tables.
- **Priority:** **Medium**.

## Readability, boundaries, and failure semantics

### 5. Prefer named construction at wide data boundaries

- **Target skill:** [python-service-architecture](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-service-architecture/references/boundaries.md).
- **Coverage:** **Missing.** The skill covers typed contracts and module ownership, but not how to map a wide row or provider response into a typed contract readably.
- **Proposed rule/guideline:** When constructing a dataclass, command, or DTO from many same-typed fields, use keyword arguments so each source is visibly matched to its destination. Consider a small named mapper at a persistence or transport boundary when the conversion is reused or includes validation. Do not introduce a new DTO merely to hide an argument list.
- **Why it should be added:** Wide positional calls are easy to misorder and hard to review, especially when multiple adjacent values are strings, integers, or timestamps.
- **Evidence/pattern observed:** [WorkRepository._owned](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/db/repositories/work.py:161) passes 22 positional values to [OwnedWork](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/domain/work.py:20), including several adjacent IDs, counts, and reconciliation timestamps.
- **Good example:** `OwnedWork(id=row.id, token=row.lease_token, client_id=row.client_id, ...)`.
- **Bad example:** `OwnedWork(row.id, row.lease_token, row.client_id, row.record_key, ...)` when the call spans many fields.
- **Exceptions / when the rule should not apply:** A short constructor with distinct arguments is often clearer positionally, such as `Point(x, y)` or a small established value object.
- **Priority:** **Medium**.

### 6. Make intentional degradation distinguishable from unexpected validation failure

- **Target skill:** [python-service-architecture](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-service-architecture/references/boundaries.md), with a pointer from [python-service-architecture-audit](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-service-architecture-audit/SKILL.md).
- **Coverage:** **Partial.** The skills require owned errors and explicit decisions, but do not say how to represent a deliberate fallback when a generic exception type also covers defects.
- **Proposed rule/guideline:** If a business action intentionally continues after a validation failure, catch the narrow, owned failure type and make the fallback outcome explicit in its result or decision. Do not use a broad built-in exception such as `ValueError` as the sole signal for a business fallback when unrelated code in the same call can also raise it. Preserve the reason code for persistence or observability when the fallback matters operationally.
- **Why it should be added:** A broad catch can turn a programming or malformed-data error into an apparently valid partial outcome.
- **Evidence/pattern observed:** [WorkExecutor._save_results](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/application/execution.py:213) catches any `ValueError` from `comment_intent` and continues with `intent = None`; the handoff then depends only on that absence. The desired graceful degradation is sensible, but the exception contract does not identify which invalid conditions permit it.
- **Good example:** `except InvalidCommentMapping as error: intent = None; reason = error.code` followed by an explicit no-delivery handoff.
- **Bad example:** `except ValueError: intent = None` around a conversion that can also fail unexpectedly.
- **Exceptions / when the rule should not apply:** At a narrow parser boundary, translating `ValueError` from one known standard-library operation is fine; a top-level process boundary may catch `Exception` to record and re-raise a terminal failure.
- **Priority:** **High**.

### 7. Extract duplicated invariant checks only when the semantics are shared

- **Target skill:** [python-service-architecture modularization](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-service-architecture/references/modularization.md) and [shared-library guidance](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-service-architecture/references/shared-libraries.md).
- **Coverage:** **Partial.** Existing text rightly rejects speculative abstraction and allows some duplication, but could state a concrete extraction trigger for duplicated validation.
- **Proposed rule/guideline:** When two operations enforce the same external identity or pagination invariant, put the shared check in a small, domain-named helper at the owning boundary. Keep operation-specific request fields, error handling, and outcomes separate. Before extracting, compare failure codes and accepted inputs; similar syntax alone is insufficient.
- **Why it should be added:** Repeated invariant checks can drift as provider behavior evolves; an oversized generic query framework would obscure the two operations.
- **Evidence/pattern observed:** [IM `record`](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/im_client/src/im_client/queries.py:242) and [IM `comment_record`](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/im_client/src/im_client/queries.py:262) repeat ambiguity, record-key, and date checks almost verbatim while requesting different field sets.
- **Good example:** A private `validated_unique_record(page, key=..., value_date=...)` used after each operation builds its own query.
- **Bad example:** A configurable query engine with callbacks and flags for just these two request shapes, or two independently maintained copies of the same identity check.
- **Exceptions / when the rule should not apply:** Keep code separate if the provider contracts or error classifications differ, even when several lines look alike.
- **Priority:** **Medium**.

### 8. Use incremental checks for bounded paginated accumulation

- **Target skill:** [python-service-architecture shared-library guidance](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-service-architecture/references/shared-libraries.md).
- **Coverage:** **Missing; deliberately narrow.** The existing skills discourage premature optimization but do not discuss repeated validation of an accumulated collection.
- **Proposed rule/guideline:** For a paginated or streaming operation that already maintains accumulated results, validate each new page once and maintain simple state such as a `seen_keys` set for cross-page invariants. Keep the bound and the final result clear. Apply this only where repeated full-prefix work grows with page count; do not add caches or complex indexes to small one-shot transformations.
- **Why it should be added:** It improves both readability and scaling by making the invariant explicit as each page arrives.
- **Evidence/pattern observed:** [SourceQueries.research](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/im_client/src/im_client/queries.py:281) rebuilds a list of all prior and new keys, then a set of the full prefix on every page despite already tracking `result` and enforcing `max_rows`.
- **Good example:** Check each page key against `seen_keys`, then update the set after the page passes validation.
- **Bad example:** `keys = [row.get("recordKey") for row in [*result, *page.rows]]` on each page.
- **Exceptions / when the rule should not apply:** A tiny, fixed-size list checked once needs no incremental state; retain the current bounded limit regardless of implementation.
- **Priority:** **Low**.

### 9. Preserve uncertain outcomes for external writes

- **Target skill:** [python-service-architecture boundaries](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-service-architecture/references/boundaries.md) and [shared-library guidance](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-service-architecture/references/shared-libraries.md); add the test oracle to [pytest worker guidance](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/pytest/references/workers.md).
- **Coverage:** **Missing as an explicit rule.** The skills discuss port-owned failures, retries, and meaningful test oracles, but do not tell an agent how to model a write whose effect is unknown after a timeout or lost response.
- **Proposed rule/guideline:** For an external write that is not provably safe to replay, distinguish confirmed success, confirmed rejection, and unknown outcome in the adapter or port contract. Treat a timeout, connection loss after dispatch, or unusable acknowledgement as unknown when the provider may have applied the write. Persist enough identity to reconcile against an authoritative read or provider idempotency key before attempting another write. Test that the uncertain path never blindly replays the side effect. Apply a simpler retry path when the provider offers a proven idempotency contract.
- **Why it should be added:** Collapsing uncertainty into an ordinary retryable error can duplicate irreversible external effects. The current code demonstrates a clear, reusable contract for this case.
- **Evidence/pattern observed:** [IM client](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/im_client/src/im_client/client.py:167) treats ambiguous write outcomes differently from read retries; [worker delivery](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/application/execution.py:245) schedules reconciliation; [unit tests](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/tests/unit/test_delivery_reconciliation.py:84) assert one send and read-only confirmation without replay.
- **Good example:** `DeliveryOutcome("delivery_unknown", "response_lost")` followed by a durable reconciliation state and an authoritative read.
- **Bad example:** `except TimeoutError: await send_comment_again()` when the first request could have succeeded.
- **Exceptions / when the rule should not apply:** Retrying is appropriate when the write is idempotent by a verified provider key or operation design, or the transport proves the request was never sent. Do not build a reconciliation subsystem for harmless, replaceable writes.
- **Priority:** **High**.

## Logging and observability

### 10. Verify that the logging schema preserves authored diagnostic fields

- **Target skill:** [python-logging implementation](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-logging/references/implementation.md) and [testing guidance](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-logging/references/testing-and-verification.md).
- **Coverage:** **Partial.** The skill requires a stable vocabulary and serialized-record tests, but does not explicitly require reconciling every call-site field with a formatter allowlist. This is a gap when the central processor silently drops unrecognized fields.
- **Proposed rule/guideline:** If a formatter uses an allowlist, review each added event's authored fields against it and verify the final serialized record contains the fields needed to answer the event's operational question. Either register the approved field with an agreed name and type or omit it at the call site; do not silently discard it. Tests should inspect representative parsed output, including retry and failure paths. Keep redaction before serialization.
- **Why it should be added:** A log statement can look informative in source while the emitted event lacks its most useful context.
- **Evidence/pattern observed:** [worker `work_deferred` logging](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/application/execution.py:125) supplies `retry_after_value`, `retry_after_seconds`, and `retry_after_received_at`. The shared [formatter allowlist](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/application_logging/src/application_logging/logging.py:17) does not include them, and [JsonFormatter.format](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/application_logging/src/application_logging/logging.py:108) drops them. The current [logging verification reference](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/.agents/skills/python-logging/references/testing-and-verification.md:23) checks serialized records but does not call out this source-to-schema check.
- **Good example:** A focused test parses one `work_deferred` event and asserts its approved `delay_seconds` or retry timestamp field is present with the documented type.
- **Bad example:** Adding `extra={"fields": {"retry_after_seconds": delay}}` without checking whether the formatter emits it.
- **Exceptions / when the rule should not apply:** Intentionally omitted sensitive or high-volume fields should stay omitted; the event catalogue should describe the safe replacement if operators still need to diagnose the outcome.
- **Priority:** **High**.

## Good practices already covered; no duplicate rule proposed

- The business policy and the async effects are separated in many places: [worker admission policy](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/domain/admission.py), [orchestrator discovery decisions](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/orchestrator/src/orchestrator/domain/discovery_policy.py), and their bootstrap loops. `python-service-architecture` already covers this ownership.
- The HTTP client accepts a monotonic clock and sleeper for deterministic retry tests, distinguishes reads from ambiguous writes, and uses bounded timeouts: [IM client](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/im_client/src/im_client/client.py:31). Existing architecture, worker, and pytest guidance cover these principles.
- Runtime resources and DB sessions have explicit async lifetimes: [orchestrator runtime](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/orchestrator/src/orchestrator/bootstrap/runtime.py), [worker transactions](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/src/worker/db/transactions.py). The DB and architecture skills already cover them.
- Tests often assert operational invariants rather than private calls: [ambiguous write tests](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/im_client/tests/unit/test_client.py:228), [lease-fencing integration test](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/services/worker/tests/integration/test_work_ownership.py:20), and [logging redaction tests](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/ControlForIM/libs/application_logging/tests/unit/test_logging.py:15). The pytest skill already states this clearly.
- Static architecture checks' three `offset` notices need semantic review before any recommendation; an offset can be a source pagination position as well as transport delivery metadata. The audit skill already warns that review notices are prompts, not proof.
