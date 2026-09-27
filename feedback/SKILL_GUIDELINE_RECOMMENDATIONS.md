# Recommendations for the Python development skills

## Scope and review basis

This is a recommendation for **skill text**, not a list of code changes. I inspected the production Python modules under `libs/` and `services/`, representative tests and configuration, and the seven named skills plus the relevant referenced guidance. The four service packages passed the architecture skill's static import checker (zero violations and zero notices each). That checker does not establish semantic correctness. Several source files were already modified in the working tree during this review, so examples describe observed patterns rather than a stable release baseline. No application code or skill was changed.

The existing architecture, pytest, settings, SQLModel, and observability skills already cover dependency direction, port-owned errors, settings/secrets ownership, avoiding speculative shared libraries, test risk selection, and logging exceptions once at the owning boundary. The recommendations below avoid restating those rules.

## 1. Typed models and configuration

### 1.1 Use `Field` when it earns its place — **High**

- **Target skill:** `python-settings-config`, especially `SKILL.md` “Core Conventions” and `references/settings-py.md` “Field Declaration Rules.” Apply the same wording to plain Pydantic models in `python-service-architecture/references/boundaries.md`; keep SQLModel column-mapping exceptions in `python-sqlmodel-alembic`.
- **Coverage:** Partially covered, but current wording says to use `Field(...)` for required settings and `Field(default=...)` for safe defaults. It also asks for descriptions on all fields. This encourages mechanical wrapping.
- **Proposed rule:** “Declare an ordinary required field as `name: Type` and an ordinary default as `name: Type = value`. Use `Field(...)` when it supplies a constraint, alias, `default_factory`, schema metadata, or a description that conveys information the name and type do not: units, format, omission behavior, or a non-obvious operational consequence. Do not add a description merely to restate the field name. A field with `Field(alias=...)` remains required without `...`. For mutable defaults, use a factory. SQLModel table fields may need `Field` for column, index, foreign-key, or server-default mapping.”
- **Why:** The shorter declaration exposes which fields have special behavior and keeps large settings models scannable.
- **Evidence:** [Ticket monitor settings](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/config/settings.py) mixes concise `pool_size: PositiveInt` and `service_version: str = "unknown"` with meaningful `Field(ge=..., le=...)` and env aliases. [Submission prep settings](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/config/settings.py) wraps many fields in description-only `Field` calls; several descriptions add useful units or semantics, while others repeat the name. [Stored documents](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/libs/db_models/src/db_models/documents.py) show useful length limits and factories, and [table models](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/libs/db_models/src/db_models/models/inbound_email.py) need `Field(sa_column=...)` for ORM mapping.
- **Good:** `pool_size: PositiveInt`; `service_version: str = "unknown"`; `retry_delay_seconds: PositiveFloat = Field(description="Delay after a transient failure.")`.
- **Bad:** `pool_size: PositiveInt = Field(description="Pool size.")` or `enabled: bool = Field(default=False, description="Whether enabled.")`.
- **Exceptions:** A generated external schema may require a description on every property. Preserve that explicit contract, but make descriptions informative.

### 1.2 Choose flat or nested settings from the current contract and cohesion — **Medium**

- **Target skill:** `python-settings-config`, “Pattern Decision / Field grouping.”
- **Coverage:** Partially covered. It says to preserve an established grouping, but also makes flat the default and requires asking before choosing grouping in a new project.
- **Proposed rule:** “Preserve the deployed env-variable names. For new settings, use flat fields while the set is small and readable; introduce nested sections when related fields are consumed and validated together or when flat names obscure ownership. Decide from the repository and deployment contract, documenting the resulting env names. Ask only when both shapes are plausible and the env contract cannot be inferred.” Remove the unconditional ask and the implication that a count of ‘several dozen+’ is the main threshold.
- **Why:** A mechanical flat default can turn a large service contract into one unrelated list, while changing an existing nested model can break env overrides.
- **Evidence:** All four application settings modules use cohesive nested sections: [ticket monitor](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/config/settings.py), [resolution worker](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/resolution-worker/src/resolution_worker/config/settings.py), [submission prep](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/config/settings.py), and [LSEG worker](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/lseg-worker/src/lseg_worker/config/settings.py). Their roots reserve aliases for deployment coordinates and group policy under names such as `queue`, `processing`, and `telemetry`.
- **Good:** `queue: QueueSettings` with `QUEUE__VISIBILITY_TIMEOUT_SECONDS` when queue policy is a coherent unit.
- **Bad:** Flattening `queue`, `database`, and `classification` into dozens of root fields solely because the skill calls flat the default.
- **Exceptions:** A small service with a handful of unrelated settings is clearer as a flat model.

### 1.3 Make cross-field and conditional configuration contracts explicit — **Medium**

- **Target skill:** `python-settings-config/references/settings-py.md`.
- **Coverage:** Partially covered by “fail early” and typed fields, but it does not tell agents how to encode relationships a field type cannot express.
- **Proposed rule:** “Use a focused model validator for relationships between fields and environment-dependent requirements; validate before constructing clients. Put independent constraints in field types or `Field`, and name the conflicting fields in the validation error. Test each meaningful invalid combination and the valid boundary.”
- **Why:** Type-level validity does not ensure a usable runtime configuration.
- **Evidence:** [Ticket monitor](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/config/settings.py) checks region agreement, digit range order, and heartbeat shorter than visibility timeout. [Submission prep](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/config/settings.py) requires a local object-store endpoint and matching AWS regions. [LSEG worker](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/lseg-worker/src/lseg_worker/config/settings.py) validates portal contact and related values.
- **Good:** A validator rejects `visibility_heartbeat_seconds >= visibility_timeout_seconds` with both field names.
- **Bad:** Accepting individually valid timeout fields and discovering their invalid relationship during the first queue message.
- **Exceptions:** Do not add a model validator for a rule already expressed clearly by one field's type or constraint.

## 2. External data and persistence

### 2.1 Validate external structure before constructing domain objects — **High**

- **Target skill:** `python-service-architecture/references/boundaries.md`, inbound adapter section.
- **Coverage:** Partially covered: it requires typed boundary contracts and rejects raw provider data in application code, but is less explicit about nested-shape validation and coercion at ingress.
- **Proposed rule:** “At a JSON, queue, HTTP, or SDK boundary, verify the shape and types of required nested fields before building a domain value. Convert malformed input to a stable boundary error. Do not use `str(value)` to make an arbitrary provider value satisfy a string contract. Preserve deliberate handling of documented alternate envelopes and test events.”
- **Why:** A typed output annotation cannot protect callers if malformed provider data is coerced or raises an incidental `KeyError`/`TypeError` during parsing.
- **Evidence:** [SQS notification parsing](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/adapters/aws/sqs_serialization.py) deliberately handles SNS wrapping and S3 test events, but then directly indexes `record["s3"]["bucket"]["name"]` and coerces bucket/key with `str(...)`. By contrast, the [EDM response boundary](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/libs/edm_client/src/edm_client/response.py) checks returned shapes and raises provider-contract errors.
- **Good:** Check that `Records` contains one mapping with nonempty string `s3.bucket.name` and `s3.object.key`, then construct `RawNotification`.
- **Bad:** `RawNotification(bucket=str(record["s3"]["bucket"]["name"]), ...)`.
- **Exceptions:** A provider may explicitly define numeric identifiers that must be converted to text; document that field-specific conversion.

### 2.2 Name the JSON serialization contract at the storage/wire boundary — **Medium**

- **Target skill:** `python-sqlmodel-alembic/references/repositories-and-queries.md`, with a short cross-reference in `python-service-architecture/references/boundaries.md`.
- **Coverage:** Missing as a practical rule. The architecture skill rejects unvalidated JSON, but neither skill states how Pydantic values become JSON-compatible documents.
- **Proposed rule:** “When a Pydantic object crosses into a JSON column, queue message, HTTP body, or checksum input, serialize deliberately with `model_dump(mode="json", ...)` or a single contract-specific serializer, and validate again on read when the stored shape is an application contract. Choose `exclude_none` and key order according to the versioned wire/storage contract. Plain `model_dump()` is acceptable for Python-only data or a proven scalar-only document; do not force JSON mode everywhere.”
- **Why:** Default `model_dump()` may retain Python objects such as `datetime`, UUID, or enum values. Mixed serialization modes also complicate equality checks and durable-document evolution.
- **Evidence:** [Response envelope persistence](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/resolution-worker/src/resolution_worker/db/repositories/responses.py) uses `model_dump(mode="json", exclude_none=True)` before hashing and writing JSON; [ticket admission](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/application/email_admission.py) uses the same mode for attachment documents. Other stored `DesiredSourceWrite` values use plain `model_dump()` in [submission prep](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/db/repositories/sessions.py) and [LSEG](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/lseg-worker/src/lseg_worker/db/repositories/submissions.py), which is currently reasonable for their scalar-only shape but makes the boundary contract implicit.
- **Good:** `document = envelope.model_dump(mode="json", exclude_none=True)` before a JSONB write and checksum.
- **Bad:** `json.dumps(model.model_dump())` when the model may contain a `datetime`.
- **Exceptions:** Do not add serialization helpers for a one-off scalar-only dictionary; name the mode at the boundary and add a round-trip test when durable compatibility matters.

### 2.3 Let query shape determine whether SQL lives in Python or `.sql` — **High**

- **Target skill:** `python-sqlmodel-alembic`, “Core conventions,” and `references/repositories-and-queries.md`.
- **Coverage:** Current rule is overly broad: it directs *all* multi-join and aggregate queries into `.sql` files, although some are clearer and safer as composable SQLAlchemy expressions.
- **Proposed rewrite:** “Keep a query inline when its filters, joins, locking, returned model type, or dialect-specific conditional update are clearer in SQLModel/SQLAlchemy. Move a long, stable reporting query to a named `.sql` file when SQL syntax itself is clearer and the file can be packaged and tested reliably. Choose by readability and ownership, not join count. Keep one query's parameters bound and its result mapping typed at the repository boundary.”
- **Why:** A forced file split hides dynamic claim predicates and typed result construction from the method that owns them.
- **Evidence:** [Rubric claims and commits](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/resolution-worker/src/resolution_worker/db/repositories/rubric.py), [inbound claims](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/db/repositories/inbound.py), and [submission queries](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/lseg-worker/src/lseg_worker/db/repositories/submissions.py) use CTEs, joins, row locking, and updates in Python to express transactional behavior. Moving them mechanically to `.sql` would make that behavior harder to trace.
- **Good:** A composable `select(...).join(...).where(...).with_for_update(...)` next to the claim method.
- **Bad:** Extracting every two-table query to a separate `.sql` file because it contains a join.
- **Exceptions:** A long reporting/aggregation query with stable SQL text often reads better as a packaged `.sql` resource.

### 2.4 Measure query-count risks without imposing one-query rules — **Medium**

- **Target skill:** `python-sqlmodel-alembic/references/repositories-and-queries.md` and `pytest/references/integration-boundaries.md`.
- **Coverage:** Partially covered by real database tests and pool guidance; missing an actionable rule for N+1 and excessive round trips in batch workflows.
- **Proposed rule:** “For a batch operation, inspect whether reads or writes scale with item count. Use bounded `IN` chunks, set-based updates, or bulk reads when they preserve clear transactional semantics. Add an operation-count regression test only for a demonstrated hot path or previously measured regression; assert a meaningful bound or scaling shape rather than a universal ‘one statement’ target.”
- **Why:** The repository has high-volume claims and batch transitions where extra round trips matter, while forcing one statement can make correctness and locking less readable.
- **Evidence:** [Submission prep session lookup](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/db/repositories/sessions.py) chunks active-ID queries at 1,000. [Operation-count integration tests](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/tests/integration/db/test_operation_count_regression.py) measure statements, checkouts, and transactions for selected claims and writes.
- **Good:** One query per bounded chunk, with a test that catches per-row database calls as input size grows.
- **Bad:** A new `SELECT` inside every iteration over a batch, or an opaque giant query solely to meet a single-statement target.
- **Exceptions:** Small, infrequent workflows may favor a couple of clear queries over additional bulk machinery.

## 3. Async execution, resources, and readable orchestration

### 3.1 Keep synchronous SDK work off the event loop and close acquired resources — **High**

- **Target skill:** `python-service-architecture/references/api-and-workers.md`, with resource examples in `python-service-architecture/references/boundaries.md`.
- **Coverage:** Lifecycle ownership is covered, but the practical async rule and per-call response-body cleanup are not stated together.
- **Proposed rule:** “If an async adapter must use a synchronous SDK, isolate the blocking call in a small synchronous method and call it via `asyncio.to_thread`; keep retries, cancellation, and concurrency limits explicit. Give every acquired client, session, browser, workbook, and streaming response an owner and close it on success and failure, preferably with a context manager or `try/finally`. Do not offload cheap pure computation by default.”
- **Why:** Blocking I/O stalls unrelated tasks, and a leaked streaming response can hold a pooled connection even after a bounded read.
- **Evidence:** [SQS adapter](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/adapters/aws/sqs.py), [raw-email store](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/adapters/aws/raw_email_store.py), and [S3 workbook store](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/adapters/s3_workbook_store.py) use `asyncio.to_thread` for boto3 calls. [Runtime composition](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/bootstrap/runtime.py) uses `AsyncExitStack` for clients and engine; [workbook parsing](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/resolution-worker/src/resolution_worker/domain/response_understanding/workbook.py) closes the workbook in `finally`. The raw-email store's S3 body is read but has no visible close owner, illustrating why the resource clause matters.
- **Good:** `async with AsyncExitStack()` for runtime resources; `try: body.read(limit) finally: body.close()` for a streaming body.
- **Bad:** Calling `boto3.get_object()` directly inside an async method, or reading a `StreamingBody` and returning without closing it.
- **Exceptions:** A documented SDK method may return fully buffered bytes or manage its own response lifetime; verify that contract before adding redundant cleanup.

### 3.2 Keep outcome decisions visible when telemetry and recovery enlarge a method — **Medium**

- **Target skill:** `python-service-architecture/references/modularization.md` and `otel-observability`, “Business telemetry.”
- **Coverage:** Partially covered: module splitting is guided by responsibilities and observability says to instrument boundaries. Neither says how to retain a readable action when tracing, metrics, retries, and logs dominate it.
- **Proposed rule:** “In a business action or consumer, keep the sequence of outcome decisions visible. When repeated telemetry/error projection obscures that sequence, extract a small helper owned by the same boundary for the repeated projection, while leaving retry, acknowledgement, and state-transition order explicit. Function length is a review signal, not a target; do not create one-call helpers or a generic telemetry framework merely to shorten a method.”
- **Why:** Reviewers need to see exactly when a message is acknowledged or a durable state changes.
- **Evidence:** [SQS consumer `_process`](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/adapters/aws/sqs_consumer.py) spans about 146 lines and repeats span marking and structured error fields across admission, heartbeat, and acknowledgement branches. [Rubric processing](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/resolution-worker/src/resolution_worker/application/response/rubric.py) and [rubric commit](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/resolution-worker/src/resolution_worker/db/repositories/rubric.py) have long, decision-heavy methods; their boundaries and transaction order matter more than a line threshold.
- **Good:** A named `record_queue_failure(...)` local to the consumer that emits the same bounded fields, with acknowledgement order still obvious in `_process`.
- **Bad:** Splitting every `if` block into a one-line wrapper or hiding acknowledgement in a generic decorator.
- **Exceptions:** A long method can remain intact when splitting it would make ordering, rollback, or lock scope harder to understand.

### 3.3 Centralize only telemetry vocabulary with a real shared contract — **Low**

- **Target skill:** `otel-observability/references/conventions/naming.md`.
- **Coverage:** Partially covered by naming consistency and ownership rules, but examples can encourage a constant for every literal.
- **Proposed rule:** “Name standard semantic-convention keys, stable event names, and values shared across emitters or tests. Keep a one-off, obvious local value near its call site when a constant adds a second lookup without protecting a contract. Group any constants by operational meaning; review large convention modules for obsolete or single-use entries, without enforcing a numeric cap.”
- **Why:** Too many indirections make a single log call harder to read and maintain.
- **Evidence:** The conventions modules are large: [ticket monitor](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/observability/conventions.py), [LSEG worker](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/lseg-worker/src/lseg_worker/observability/conventions.py), [resolution worker](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/resolution-worker/src/resolution_worker/observability/conventions.py), and [submission prep](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/observability/conventions.py). A source-only reference count found many constants used once in the same service, particularly in LSEG and submission prep. The stable event and attribute names used by multiple sites remain good candidates for constants.
- **Good:** A shared `EVENT_QUEUE_MESSAGE_FAILED` or `ATTR_ERROR_TYPE` used across emitters and tests.
- **Bad:** A module-level alias for a literal used once in one nearby log statement when its name adds no meaning.
- **Exceptions:** A single-use value can still deserve a constant when it is a published wire name, semantic-convention key, or externally queried log event.

## Rules reviewed and already sufficient

- **Architecture and dependency injection:** `python-service-architecture` and `python-service-architecture-audit` already distinguish application decisions, ports, concrete adapters, bootstrap composition, and speculative abstraction. [Ticket admission](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/ticket-monitor/src/ticket_monitor/application/email_admission.py) and [runtime composition](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/src/submission_prep/bootstrap/runtime.py) provide good examples. No duplicate rule is proposed.
- **Exception translation and one owning log:** `python-service-architecture/references/boundaries.md` and `otel-observability/references/conventions/errors.md` already cover specific port errors, chained causes, and one boundary log. Broad `except Exception` in a top-level consumer is not automatically a defect; it can correctly prevent acknowledgement and schedule redelivery. No blanket ban is proposed.
- **Tests:** `pytest` already demands stable behavior oracles, hermeticity, bounded async waits, real database tests for database claims, and no implementation-mirroring tests. [EDM client tests](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/libs/edm_client/tests/test_retry.py) and [database operation-count tests](/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Opus/1008-exceptions/1008-automation/services/submission-prep/tests/integration/db/test_operation_count_regression.py) illustrate these practices. The query-count recommendation above adds only the missing batch-performance trigger.
- **Shared libraries and duplicated settings loaders:** The four settings modules repeat YAML merge/discovery code, but `python-repository-setup` and `python-service-architecture/references/shared-libraries.md` already require demonstrated stable reuse, explicit inputs, and consumer migration before extraction. That is the right guardrail; do not add a blanket “deduplicate settings loaders” rule.
- **Naming, comments, imports, and module size:** The repository's `AGENTS.md` and `python-service-architecture/references/modularization.md` already treat focused functions, useful comments, and file size as review signals. The recommendation above only sharpens the special case where telemetry obscures operational ordering. Cosmetic naming or import changes do not warrant new skill rules from this review.

## Suggested edit order

1. Rewrite the settings `Field` guidance and examples, then adjust the flat/nested decision text.
2. Rewrite the SQL extraction rule, since the current absolute wording conflicts with transactional repository patterns.
3. Add inbound validation, JSON serialization, and async resource-lifetime guidance at their respective boundaries.
4. Add the narrower performance, orchestration-readability, and telemetry-vocabulary guidance where it fits without duplicating existing rules.
