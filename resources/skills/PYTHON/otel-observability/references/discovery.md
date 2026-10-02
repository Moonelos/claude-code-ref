# Discovery

Answer these before editing code. Most have a default you may take silently — those are marked **Default**. Items marked **Ask** require confirmation when their stated condition applies; guessing them produces telemetry or deployment architecture that is wrong rather than incomplete.

Record the answers in your first message so the user can correct a wrong assumption cheaply.

## Contents

- [Service and deployment identity](#1-which-service)
- [Application type](#2-what-type-of-application-is-it)
- [GenAI path](#3-does-it-use-genai-and-through-what)
- [Asynchronous work](#4-does-it-publish-or-consume-asynchronous-work)
- [Baggage](#5-is-this-a-rootstart-application-that-must-introduce-baggage)
- [Backends](#6-which-observability-backends--ask)
- [Export topology](#7-how-should-telemetry-be-exported--ask-when-deployment-is-in-scope)
- [Production policy inputs](#8-is-the-target-production-or-is-samplingfiltering-being-changed)
- [Business telemetry](#9-what-business-telemetry-is-worth-adding)
- [Report template](#report-template)

---

## 1. Which service?

Find the service's entry point, its dependency manifest, and its existing config module. In a monorepo, confirm the exact directory before touching anything.

**Ask** if the repo holds more than one service and the user did not name one.

What to look for:

```
entry point       app.py / main.py / worker.py / handler.py / __main__.py
config            config.py / settings.py / core/config.py
dependencies      pyproject.toml / requirements.txt
existing telemetry  grep for opentelemetry, structlog, logging.config, langfuse
```

If the service already has partial instrumentation, extend it. Do not create a parallel provider — see `setup/sdk_bootstrap.md`.

### Deployment identity

Inspect the Dockerfile, Compose file, Helm chart or Kubernetes manifests, ECS
task definition, Lambda/SAM/CDK/serverless configuration, and CI workflow that
build and run this service. Record:

```text
service.namespace       stable application/system grouping
service.name            logical API, worker, or job name
service.version source  Git SHA, release, or immutable image build
instance ID source      process UUID, Pod UID, container ID, ECS task/container,
                        or Lambda execution-environment UUID when required
```

Read `setup/resource_identity.md` before implementing the `Resource`. Do not
assume one instance-ID source works across every deployment target. Then read
only the runtime file selected by `SKILL.md`. If several runtimes are present,
document one owner for each. Multi-process identity is an additional condition,
not an alternative to the container platform. If CI already exposes a Git SHA,
prefer that over computing a version from the runtime filesystem.

---

## 2. What type of application is it?

The type decides the tracing boundary — where a trace starts, and what its root span means.

| Type | Trace boundary | Read |
| --- | --- | --- |
| HTTP/API service | Inbound request; server span is the root and auto-instrumentation owns it | `tracing/http_service.md` |
| Long-running background worker | Process lifecycle plus the unit-of-work transport | `tracing/worker_runtime.md`, then the matching handoff row below |
| Direct queue consumer | One message; parent-or-link decision required | `tracing/async_handoffs.md` + `tracing/queue_messaging.md` |
| DB-backed worker / durable state machine | One claimed work item or runnable transition; parent-or-link decision required | `tracing/async_handoffs.md` + `tracing/durable_work.md` |
| Scheduled job / CLI batch | One run; always a new root, must flush on exit | `tracing/scheduled_jobs.md` |
| AWS Lambda | One managed invocation; trigger-specific parent/link semantics and force-flush before freeze | `tracing/lambda_functions.md` |
| Agentic application | The agent invocation, usually inside an HTTP or worker boundary | `tracing/genai/langchain/architecture.md` |
| Simple LLM application | The single model call, inside whatever boundary calls it | `tracing/genai/provider_sdk.md` |
| Other backend service | The operation the service exists to perform | `tracing/http_service.md` for shape |

A service can be more than one of these — an API that also runs a consumer is two boundaries in one process. Instrument both, with one provider.

---

## 3. Does it use GenAI, and through what?

Either way, start at `tracing/genai/attributes.md` — it holds the span vocabulary both paths use — then take the row that matches:

| Signal in the code | Path |
| --- | --- |
| `langchain`, `langgraph`, `create_agent`, `ChatOpenAI`, callbacks | LangChain path — `tracing/genai/langchain/architecture.md` |
| `openai`, `anthropic`, `boto3` `bedrock-runtime`, `google.genai`, `azure.ai` | Direct SDK path — `tracing/genai/provider_sdk.md` |
| Both | Instrument each call site with the path that matches it. Do not double-instrument one model call. |
| Neither | Skip `tracing/genai/` entirely, and `metrics/genai.md` with it |

If a model call is already traced by a framework integration or gateway, do not add a second span around it. Duplicate generations inflate token and cost analytics.

---

## 4. Does it publish or consume asynchronous work?

**Default:** no, unless you find either:

- a queue/broker client (`boto3` SQS/SNS, `kombu`, `pika`,
  `confluent_kafka`, `celery`, Redis streams, `google.cloud.pubsub`); or
- database-backed work coordination: polling/claim loops, outbox or inbox
  tables, `FOR UPDATE SKIP LOCKED`, lease columns, `next_run_at`, or persisted
  state-machine transitions that a different process resumes.

If it **publishes queue work**: read `tracing/async_handoffs.md` and
`tracing/queue_messaging.md`. If it **schedules durable DB work**: read
`tracing/async_handoffs.md` and `tracing/durable_work.md`. The producer or
transition span must inject trace context into the queue message or durable
database record. Store the carrier atomically with the work item/state change.

If it **consumes or resumes work**: **Ask** — *how does the worker receive the
propagated trace context?* You need the concrete carrier:

```
HTTP-style headers on the message?
SQS MessageAttributes?
Kafka record headers?
A named field inside the JSON body, e.g. body["_trace"]?
A string-to-string JSON/JSONB field on the work row?
Dedicated `otel_traceparent` and `otel_tracestate` columns?
Nothing — the producer is not instrumented?
An AWS-managed trigger carrier such as SQS `AWSTraceHeader`?
```

The answer changes real code, not just a comment:

| Answer | Consequence |
| --- | --- |
| A string→string header map | `propagate.extract(headers)` works directly |
| SQS `MessageAttributes` | Requires the `Boto3SQSGetter` carrier adapter, and `MessageAttributeNames` must be requested on receive or the fields never arrive |
| A field inside the payload | Extract that sub-dict as the carrier; document the field name as a contract |
| A DB carrier field or W3C columns | Reconstruct a string→string carrier, extract it from an explicit empty context, then choose parent or link; persist `traceparent` plus optional `tracestate`, not a bare trace ID |
| Producer is not instrumented | The consumer starts a genuinely new root trace. Say this explicitly rather than silently producing orphans. |
| AWS Lambda trigger | Let the selected Lambda instrumentation own the invocation; verify trigger extraction/links using `tracing/lambda_functions.md` rather than copying a polling loop into the handler |

The database client span for the worker's `SELECT`/claim operation is transport
detail, not the causal producer of the work. Never make processing a child of a
polling span; use the context stored with the claimed row.

Then decide parent-or-link per `tracing/async_handoffs.md`, "Decide
parent-or-link first", and record the choice. For a long-lived state machine, also locate its
stable `workflow_run_id`/job ID. Put that identifier on spans and important
logs for end-to-end search, never on metrics.

---

## 5. Is this a root/start application that must introduce baggage?

**Default: no baggage.** Assume none is required unless the user names the values.

Introduce baggage only when a value is (a) decided at this service, (b) needed by a *different* service, and (c) small, bounded, and non-sensitive. Trace context alone already connects the spans — baggage is for extra request facts, and it is not free: it rides in every outbound header.

**Do not open `tracing/baggage.md` to make this decision.** The decision is made here, and the answer is no unless the user named values that must travel between services. Open the file only after that condition is met; it is an implementation guide, not a rationale for adding baggage.

When you do: never propagate tokens, keys, emails, prompts, documents, or unbounded user input.

---

## 6. Which observability backends? — **Ask**

There is no default. Do not infer a backend from a stray environment variable or a docker-compose file without confirming.

Ask for one destination per signal:

```
traces  -> ?
metrics -> ?
logs    -> ?
```

Common answers: Grafana Tempo, Grafana Mimir/Prometheus, Grafana Loki, Langfuse, Datadog, New Relic, Honeycomb, Jaeger, AWS X-Ray, CloudWatch, Azure Monitor, or another OTLP-compatible vendor.

A Collector is transport and processing infrastructure, not the final backend.
If the user answers "a Collector," still ask where it forwards each signal.
Collector-mediated routing is often useful in production, but direct OTLP export
may also be appropriate. Confirm the intended topology in §7.

Note the split that matters for GenAI services: **Langfuse is a trace and LLM-workflow backend, not a metrics backend.** Operational metrics and alerts go to a metrics backend; Langfuse receives traces, generations, scores, and cost, as a projection of the same trace (`collector/genai_projection.md`).

---

## 7. How should telemetry be exported? — **Ask when deployment is in scope**

Do not assume that a deployed service requires an OpenTelemetry Collector. Direct OTLP export and Collector-mediated export are both valid production architectures. Either way telemetry leaves by OTLP push: never add a Prometheus pull reader or scrape endpoint, in the application or the Collector.

Preserve an established export topology when one already exists. Otherwise, when deployment manifests, credentials, exporter routing, or Collector configuration are in scope, ask the user to choose:

- direct OTLP export from the application to each backend;
- a Collector colocated with the application: a sidecar per application replica, or an agent per host or Kubernetes node;
- a shared gateway Collector; or
- colocated Collectors forwarding to a gateway Collector.

Recommend a Collector when concrete requirements include centralized credentials, redaction, transformation, fan-out, protocol conversion, tail sampling, stronger buffering, or organization-wide telemetry policy. Explain its operational cost as well as its benefit.

If deployment topology is outside the requested scope, keep the OTLP endpoint configurable and do not add a Collector component without asking. If a Collector is selected, read `collector/component.md`. It is its own deployable component (`services/otel-collector/` or the repo's equivalent), with separate configs for development, staging, and production.

---

## 8. Is the target production or is sampling/filtering being changed?

**Default:** no production retention change unless the user requests production,
sampling, filtering, telemetry cost reduction, release burn-in, or rollout work.
When any of those applies, read `tracing/production_policy.md` and collect:

```text
new traces/second                    fleet and per high-volume route/workflow
average and p95 spans/trace          including long agent traces
p99 complete-trace arrival time      duration plus SDK/export/network jitter
error and slow-trace rates           from full-fidelity metrics, not traces
serialized bytes/span or trace       measured at the SDK or Collector
critical outcomes                    routes, workflows, blocks, costly outcomes
backend ingest/retention budget      volume or cost ceiling
minimum useful daily sample          per route/workflow, especially low volume
Collector topology                   replicas and trace-ID affinity
outage buffer objective              how long queued export should absorb
```

Do not silently substitute `5%`, `30s`, `50000` traces, or any token/latency
threshold from an example. If measurements are unavailable, produce a clearly
marked provisional policy and state exactly what must be measured before the
configuration is production-ready. A production sampling configuration cannot
be called complete while its percentage and capacity are unjustified.

For deterministic noise, identify each candidate route or span and record:

- whether failed instances still need trace visibility;
- whether the operation has instrumented children;
- whether source exclusion also suppresses useful HTTP metrics;
- whether the rule is service- and route-specific rather than a global span-name match.

For forced diagnostics, record the trusted internal control that will set them;
the requirements are in `tracing/production_policy.md`, "Critical outcomes and
diagnostics".

---

## 9. What business telemetry is worth adding?

Read the service's actual business logic before answering. Look for: the domain nouns in the module and function names, the identifiers that appear in existing log lines, the branches that decide success versus failure, the counters or totals the code already computes.

Turn those into a short list of candidates, then keep only the ones that pass this test — the value must plausibly be used for **debugging, filtering, aggregation, incident investigation, performance analysis, or business monitoring**. Availability is not a reason.

Split them by signal:

| Signal | Good candidate |
| --- | --- |
| Span attribute | A bounded fact describing one operation: `app.pricing.product_count`, `app.exception.rule` |
| Metric | A rate or distribution you would alert or trend on: `app.exception.reviews` |
| Log field | A high-cardinality identifier needed to find one record later: `exception_id`, `order_id` |

If the user explicitly requested particular business attributes, include them as well.
Exception detail follows the `python-logging` skill; ask only
when the service handles personal or financial data and no policy is stated.

---

## Report template

Post this back before you start editing:

```
Service:        services/pricing-worker
Type:           SQS queue consumer
Resource:       namespace=pricing; version=Git SHA; instance=ECS TaskARN
GenAI:          none
Messaging:      consumes pricing-jobs; trace context in SQS MessageAttributes
Trace policy:   new trace + link to producer (jobs are retried independently)
Baggage:        none
Backends:       traces -> Tempo, metrics -> Mimir, logs -> Loki
Export topology: shared gateway Collector, new services/otel-collector component
Business:       app.pricing.product_count, app.pricing.updates, supplier_id log field
Error detail:   safe projection in prod YAML; full in dev YAML (policy: <source>)
Production:     <not measured — PROVISIONAL; see §8 for the required inputs>
Noise:          successful /live and /ready are leaf spans; failed probes retained
Rollout:        release burn-in for one Git SHA; owner=platform; expires=<date>
```

The `Production:` line is deliberately a placeholder. Fill it in only from
measurements you actually have, and keep the literal word **PROVISIONAL** on it
until every input in §8 exists. A filled-in shape is read as a measurement; if
you write `120 traces/s` because the template had a number in it, someone will
size a sampler from it. When measurements do exist, the line looks like:

```
Production:     MEASURED 2026-08-11: 120 traces/s; p99 complete arrival 18 s;
                errors/slow/checkout 100%; normal successes 3%
```

Anything you had to assume, mark as an assumption so it is cheap for the user to correct.

For a DB-backed state machine, report the durable carrier and business
correlation explicitly:

```text
Service:        services/order-worker
Type:           DB-backed durable state machine
Durable work:   claims order_transitions; W3C carrier in otel_context JSONB
Trace policy:   new trace per attempt + link to scheduling transition
Correlation:    app.workflow.run.id on spans; workflow_run_id on boundary logs
Baggage:        none
Backends:       traces -> Tempo, metrics -> Mimir, logs -> Loki, all via Collector
```

For Lambda, record managed-runtime ownership explicitly:

```text
Service:        functions/pricing-handler
Type:           AWS Lambda, SQS event source mapping
Invocation:     opentelemetry-instrumentation-aws-lambda owns one batch span
Messaging:      producer context in AWSTraceHeader; one linked child per message
Export:         local Collector extension -> OTLP backend
Propagators:    tracecontext (add baggage only for explicitly approved values; no xray-lambda)
Flush:          instrumentation force-flush before Lambda freeze
Resource:       faas.name/version from Lambda detector; service.version from CI
```
