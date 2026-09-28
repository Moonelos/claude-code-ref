---
name: python-logging
description: Add, audit, repair, or standardize low-noise structured application logging and meaningful operational or business events, including exception ownership, correlation, redaction, and verification. Use for services, workers, jobs, CLIs, and GenAI applications whether logs go to stdout, files, a platform log service, or a vendor backend; OpenTelemetry and OTLP are optional and are not introduced unless the user requests them.
---

# Python Logging

Make an application's behavior searchable through a small, intentional catalogue of structured events. Preserve what the application does and its established log destination. This skill owns application logging, including when the service also uses OpenTelemetry for traces and metrics; `$otel-observability` owns only the trace-context enricher and log–trace correlation rules (fallback `../otel-observability/references/logging/correlation.md`).

## Scope

Work on one user-named service by default. In a monorepo, ask which service only when the target cannot be inferred. Extend the existing logging configuration instead of creating a competing pipeline. Shared-library or cross-service changes require explicit scope; inspect all current consumers before changing a shared schema or processor.

Do not require OpenTelemetry, an OTLP exporter, or a Collector. When valid trace context already exists, enrich records with its `trace_id` and `span_id`. When it does not, logs remain complete using the execution and business correlation already available, such as `request_id`, `job_id`, or `workflow_run_id`. Never fabricate trace identifiers.

## Choose the work mode

| Mode | Read |
| --- | --- |
| Add or standardize logging | All references except `genai.md` (unless the application uses GenAI) and `structlog-pipeline.md` (skip it only when logging is built on another library, such as loguru or a vendor SDK) |
| Audit or review | `event-design.md`, `implementation.md`, `errors-and-security.md`, and `testing-and-verification.md`; add `genai.md` when applicable |
| Repair a concrete symptom | The matching section in `testing-and-verification.md`, then the reference that owns the failed invariant |
| GenAI logging | The normal references plus `genai.md` |

## Discovery

Before editing, inspect the service entry point, configuration, dependency manifest, deployment/runtime files, existing logging setup, exception boundaries, request/job middleware, and representative business paths. Determine:

- which module currently owns logging configuration;
- the runtime boundaries: HTTP requests, queue messages, jobs, workflow transitions, CLI runs, or serverless invocations;
- the existing sink and delivery path: stdout/stderr, file, syslog, platform agent, cloud handler, or vendor SDK;
- the identifiers already used for execution and business correlation;
- the repository's privacy/redaction policy and known secrets or payloads;
- the business decisions, state changes, retries, and failures operators actually need to find.

Preserve an established sink. If delivery configuration is explicitly in scope and no destination has been chosen, ask rather than selecting a vendor. If only application logging is in scope, default to one-line JSON on stdout/stderr and leave collection outside the change.

## Invariants

1. **One logging owner.** Configure formatting, filtering, enrichment, redaction, and exception policy centrally. Application modules obtain named or bound loggers; they do not call global configuration.
2. **Machine-readable production output.** Emit one JSON object per record. Human-readable development output is optional, but it must represent the same schema and must not change event decisions.
3. **Stable event identity.** The log call's first positional argument is the `event`: a low-cardinality snake_case past-tense or state-change name such as `job_failed` or `payment_declined`, never a sentence with values. Runtime values belong in fields. Call-site rules (module logger, one call-site API per repo): `references/implementation.md#Call sites`.
4. **Meaningful events only.** Log boundaries, material state changes and decisions, external side effects, retries/fallbacks, and terminal failures. Do not mirror control flow, function entry/exit, loop iterations, or every successful dependency call; repeated loop failures follow `references/event-design.md#Loops and pollers`.
5. **A record explains itself.** Include UTC timestamp, normalized `level` (or the repository's established severity field), event, service identity, and the bounded context needed to group the occurrence. Add permitted high-cardinality IDs only when they help locate this occurrence.
6. **Correlation is additive.** Propagate and bind the repository's request/job/workflow context. Add active `trace_id`/`span_id` when available, but do not make logging depend on tracing.
7. **One terminal failure record.** The boundary that decides the operation's final outcome emits exactly one error record with `exc_info`. Inner layers enrich and re-raise without `exc_info`; recovered retries are counted, and an activated fallback may emit one warning. Details: `references/errors-and-security.md#Failure record contract`.
8. **Central exception detail policy.** Call sites pass `exc_info` and never build `exception.*` fields; the central processor applies one typed exception-detail setting whose value is set per environment in YAML, never derived from the environment name in code. This skill owns the rule: `references/errors-and-security.md#Exception detail`.
9. **Data minimization.** Never log credentials, tokens, cookies, authorization headers, full request/response bodies, or arbitrary payloads. Personal data and content require explicit policy and purpose. Redaction runs centrally and recursively before serialization.
10. **Severity has semantics.** `debug` is diagnostic; `info` is a normal material occurrence; `warning` is degraded but handled; `error` is a failed owned operation; `critical` is process/service viability loss. Do not use severity to describe business importance alone.
11. **Schema consistency.** One fact has one field name and compatible value type across the service. Prefer established semantic names when present; otherwise use the repository's namespace. Do not scatter field-name literals when a shared vocabulary already exists. A field allowlist never silently drops authored fields: `references/implementation.md#Field allowlists`.
12. **Volume is designed.** Never sample terminal failures or audit-relevant state changes. Omit or sample known noisy success events deliberately, with deterministic or rate-based policy documented at the central boundary.

## Workflow

1. Read [`references/event-design.md`](references/event-design.md) and derive a small event catalogue from actual business code. For every event, state the operational question it answers.
2. Read [`references/implementation.md`](references/implementation.md). Extend the current logging owner, define the canonical envelope and context lifecycle, then migrate only relevant call sites. For a structlog/stdlib repo, [`references/structlog-pipeline.md`](references/structlog-pipeline.md) is the reference pipeline.
3. Read [`references/errors-and-security.md`](references/errors-and-security.md) before changing exception logging, redaction, privacy behavior, or high-cardinality fields.
4. If the service calls a model or runs an agent, read [`references/genai.md`](references/genai.md).
5. Read [`references/testing-and-verification.md`](references/testing-and-verification.md), add focused tests where a suite exists, capture representative output, and verify the real sink when delivery is in scope.

## Completion report

Report the service and boundaries changed, the logging owner and sink preserved, the event catalogue added or changed, correlation fields, exception/redaction policy, tests run, and real output or sink verification. State any unverified delivery path or assumed privacy rule plainly.
