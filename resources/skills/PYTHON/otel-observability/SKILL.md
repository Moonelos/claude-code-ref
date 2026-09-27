---
name: otel-observability
description: "Add, audit, repair, upgrade, or troubleshoot OpenTelemetry tracing, metrics, and log–trace correlation in a Python service or shared observability library — FastAPI/HTTP APIs, workers, queue consumers, DB-backed state machines, scheduled jobs, AWS Lambda, LangChain/LangGraph agents, and direct LLM SDK calls. Covers GenAI semantic conventions, token and TTFC capture, trace propagation across queues and durable DB handoffs, baggage, the OpenTelemetry Collector, and OTLP backend routing. Use to instrument a service, fix or review spans and metrics, or investigate missing or duplicate signals. Application logging itself belongs to python-logging."
---

# Observability Implementation

You are making working software's behaviour visible without changing what it
does. This file is a router plus a rule index; each rule is stated once, in the
file the index names. **Load only the files the routing sends you to.**

## Scope

- **One service at a time.** Instrument the service the user named. If none is
  named and the repo has more than one service, ask first. Shared code changes
  stay additive.
- **Sibling consistency.** When sibling services already have `observability/`,
  read their public helper signatures first and reuse them verbatim. Helper API
  consistency is in scope even when editing siblings isn't.
- **Duplicated plumbing** (provider lifecycle, logging processors, propagation)
  is resolved by the extraction triggers in the `python-service-architecture`
  skill (`../python-service-architecture/references/shared-libraries.md`, Extraction triggers).
  Extract into a shared library only when the task's scope includes it
  (`references/setup/shared_library.md`); otherwise report the finding.
- **Python, FastAPI for HTTP.** For another runtime use only the conventions,
  retention policy, and Collector material.

## Step 0 — Pick the mode

| Mode | Load |
| --- | --- |
| **Add** instrumentation | Step 1, then Step 3 routing |
| **Audit or review** | `references/conventions/naming.md`, `references/conventions/errors.md`, `references/metrics/service.md`, `references/logging/correlation.md`, `references/verification.md`, the matching boundary file; run `scripts/audit_telemetry.py <src>` |
| **Troubleshoot** a symptom (missing, duplicated, orphaned, zero-valued signals) | `references/troubleshooting.md`, then the one file it names |
| **Upgrade** a package, convention revision, or Collector image | `references/compatibility.md`, then the files its checklist names |
| **Collector-only** change | `references/collector/*`; `references/tracing/production_policy.md` for retention |
| **Shared observability library** | `references/setup/shared_library.md` |

## Step 1 — Discovery

Read `references/discovery.md`. Two questions block work: which backends
receive traces, metrics, and logs (never guess), and, for a consumer, worker,
durable state machine, or event-driven Lambda, how trace context arrives. When
deployment or exporter routing is in scope, also ask the export topology
(direct OTLP, colocated Collector, gateway). Production sampling needs measured
traffic; never turn example numbers into defaults.

## Step 2 — Minimum viable instrumentation, then the rules

Start with this and stop here unless a named consumer needs more:

- **boundary spans**: one span per request, message, job, durable transition,
  model or tool call, via the shared `start_span` helper;
- **one error helper**: `start_span` / `mark_error` from
  `references/conventions/errors.md`;
- **a few outcome metrics**: throughput, failures, and duration per boundary;
- **owner logs**: per the `python-logging` skill, with trace IDs from
  `references/logging/correlation.md`.

Every further layer (child spans, per-item attributes, extra instruments,
events) names the query, dashboard, alert, or investigation it serves and its
expected volume.

### Rule index

| # | Rule | Owner |
| --- | --- | --- |
| 1 | Repository guidance wins over examples here, except the OTLP-push policy (rule 13). Check version-sensitive examples first. | `references/compatibility.md` |
| 2 | No span events. Failures: `ERROR` status plus bounded `error.type`, set by `start_span`. | `references/conventions/errors.md` |
| 3 | Semantic conventions first, `app.*` otherwise; never invent keys in a standard namespace. Shared names are constants. | `references/conventions/naming.md` |
| 4 | Span names are low-cardinality; dynamic values are attributes. Never build keys from runtime values. | `references/conventions/naming.md` |
| 5 | One owner per boundary: auto-instrumentation, framework integration, or your code, never two. | `references/setup/auto_instrumentation.md` |
| 6 | New settings go into the service's settings object, per the `python-settings-config` skill. | `references/setup/package_layout.md` |
| 7 | SDK setup and framework adapters live in separate modules of `observability/`; nest only under demonstrated pressure. | `references/setup/package_layout.md` |
| 8 | Content capture is off by default; system instructions and history are split as the provider receives them. | `references/tracing/genai/content_capture.md` |
| 9 | Exception detail: call sites pass `exc_info=exc` only; one setting, set per environment. Spans never carry it. | `python-logging` (`../python-logging/references/errors-and-security.md`, Exception detail) |
| 10 | Metrics are independent of trace sampling, with bounded attributes; one measurement, one instrument, one producer. | `references/metrics/service.md` |
| 11 | Instrument boundaries, not functions. DB/ORM spans must earn their volume. | `references/setup/high_volume_database_tracing.md` |
| 12 | Durable handoffs carry an allowlisted W3C carrier. Synchronous in-process call → parent; outbox publish → link; queue redelivery → link plus `app.message.attempt`. | `references/tracing/async_handoffs.md` |
| 13 | OTLP push to the Collector is the default; no Prometheus pull readers or scrape endpoints. | `references/collector/component.md` |
| 14 | A GenAI backend is a rooted projection of the same trace, not a second provider or trace. | `references/collector/genai_projection.md` |
| 15 | Telemetry never chooses or mutates an outcome; no `try/except` around OTel API calls. | `references/conventions/errors.md#telemetry-failure-isolation` |
| 16 | Application code uses one-line telemetry helpers only (≈3 lines per call site); one `work_boundary`-style helper closes span, log, and metric on every exit. | `../python-service-architecture/references/boundaries.md` |
| 17 | Spans are write-only; `gen_ai.usage.*` only on model-call and agent spans; no spans as events (log plus counter); don't copy `http.*` onto internal spans. | `references/tracing/genai/attributes.md` |
| 18 | All application logging is owned by the `python-logging` skill (`../python-logging/SKILL.md`); this skill owns only the trace-context enricher and log–trace interactions. No OTLP log export. | `references/logging/correlation.md` |

Load conditionally: `references/tracing/baggage.md` only when the user names
values that must travel between services; `references/testing.md` when the repo
has tests and the work adds parsing, serialization, redaction, streaming,
retry, or propagation logic.

## Step 3 — Route to references

Work **tracing → metrics → logging → collector**, loading each file when you
reach its part.

| Situation | Load |
| --- | --- |
| Creating or changing SDK setup | `references/setup/resource_identity.md`, `references/setup/package_layout.md`, `references/setup/auto_instrumentation.md`, `references/setup/sdk_bootstrap.md` |
| Runtime identity | `references/setup/resource_kubernetes.md`, `resource_docker_compose.md`, `resource_ecs.md`, or `resource_processes.md` (multi-process, or no platform identity) |
| Process startup | FastAPI `references/setup/startup_fastapi.md`; worker/CLI `startup_worker_cli.md`; pre-fork `startup_prefork.md` + `resource_processes.md` |
| HTTP/API service | `references/tracing/http_service.md` |
| Long-running worker | `references/tracing/worker_runtime.md` |
| Scheduled job or CLI batch | `references/tracing/scheduled_jobs.md` |
| AWS Lambda (identity, startup, tracing) | `references/tracing/lambda_functions.md` |
| Queue publish or consume | `references/tracing/async_handoffs.md`, then `references/tracing/queue_messaging.md` |
| DB-backed queue, outbox, lease, state transition | `references/tracing/async_handoffs.md`, then `references/tracing/durable_work.md` |
| Production sampling, cost, rollout | `references/tracing/production_policy.md` (before any production Collector config) |
| Any GenAI code | `references/tracing/genai/attributes.md` first (entry point for `tracing/genai/`) |
| — token counts / payload capture | `references/tracing/genai/token_usage.md` / `references/tracing/genai/content_capture.md` |
| — direct provider SDK | `references/tracing/genai/provider_sdk.md` |
| — LangChain or LangGraph | `references/tracing/genai/langchain/architecture.md`, then only the layers you build |
| — RAG embedding and retrieval | `references/tracing/genai/retrieval.md` |
| Metrics | `references/metrics/service.md`; GenAI adds `references/metrics/genai.md` |
| Logging | the `python-logging` skill for the logs themselves, plus `references/logging/correlation.md` for trace IDs |
| Deploying a Collector | `references/collector/component.md`, `dev_staging.md`, `production.md`; `genai_projection.md` for a GenAI backend view |
| Before reporting done | `references/testing.md` (when applicable), then `references/verification.md` |

Handoff tables compose: an HTTP endpoint that publishes to a queue loads both.
`references/local/` holds repository-specific mappings; load only on a match.
`scripts/estimate_trace_budget.py` gives production volume lower bounds.

## Step 4 — Business telemetry

Read the business logic and add the few attributes, metrics, and log fields
someone would use in an incident. For each candidate, name the question it
answers; availability is not a reason. Prefer domain words
(`app.pricing.product_count`, not `processed_items`). Never hold one span open
around a worker loop: each message, job, batch, or attempt gets a bounded
trace. High-cardinality IDs go on spans and logs when policy allows, never on
metrics.

## What not to do

- Don't put a model name, tool name, prompt, user ID, or request ID into a span name.
- Don't enable every auto-instrumentation package; noisy ones such as full `botocore` need a stated reason.
- Don't create a second `TracerProvider`, or mix `opentelemetry-instrument` with in-code setup.
- Don't create a span per streamed token, or hold `start_as_current_span` across a generator `yield`.
- Don't copy example sampling percentages, thresholds, or capacities into production.
- Don't accept a force-sampling signal from an untrusted request, message, or baggage carrier.
- Don't pick a backend for the user, and don't report done before `references/verification.md`.
