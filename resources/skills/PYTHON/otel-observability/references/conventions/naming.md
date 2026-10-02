# Naming: Spans, Attributes, Metrics, Log Events

One rule underpins all of these: **the name is the low-cardinality part, the value is the variable part.** A name that varies per request destroys aggregation in every backend.

---

## Priority order

Whenever you need a name, work down this list and stop at the first hit:

```
1. An OpenTelemetry semantic convention exists       -> use it verbatim
2. No convention exists, the fact is organisational  -> app.<domain>.<thing>
3. The user asked for a specific name                -> use theirs, note the deviation
```

Never invent a key inside a standard namespace. `gen_ai.usage.input_token_details` looks official and is not; it belongs under `app.gen_ai.usage.input_token_details`. A backend that ships support for the real attribute later will then not collide with yours.

---

## Span names

Format: **operation, then a stable subject**. No IDs, no user input, no prompt text.

| Good | Bad | Why the bad one hurts |
| --- | --- | --- |
| `GET /orders/{order_id}` | `GET /orders/12345` | One span name per order |
| `process exception` | `process exception 931272` | Unaggregatable |
| `invoke_agent support_agent` | `agent invocation` | Loses which agent when there are several |
| `chat gpt-5` | `chat` | Cannot compare models |
| `execute_tool web_search` | `tool call` | Cannot find the failing tool |
| `send pricing-jobs` | `publish message` | Loses the queue |
| `process pricing-jobs` | `worker loop` | Describes the code, not the operation |
| `run workflow transition` | `run transition wf-123` | Puts a workflow-run ID in the name |

GenAI spans follow the semantic convention shape `{gen_ai.operation.name} {subject}`:

```
chat gpt-5
embeddings text-embedding-3-small
retrieval product_docs
execute_tool order_lookup
invoke_agent support_agent
invoke_workflow support_rag
```

Tool names come from the model and are therefore untrusted. If users can define arbitrary tools, map unknown names to a bounded value such as `custom_tool` before they reach a span name or metric attribute, and keep the raw name in an attribute.

---

## Span attributes

Rules:

- lowercase, dot-separated namespaces;
- stable keys — never build a key from a runtime value (`user.abc123.count` is a leak, not an attribute);
- bounded values wherever the value will be filtered on;
- no arbitrary payloads; a serialized blob belongs behind a content-capture flag or not at all;
- domain vocabulary over implementation vocabulary.

Prefer the word the business uses:

```
app.pricing.product_count        not   processed_items
app.exception.rule               not   rule_str
app.retrieval.result_count       not   n
```

### Namespaces you will actually use

| Namespace | Owner | Examples |
| --- | --- | --- |
| Resource attributes | OTel | `service.name`, `service.version`, `deployment.environment.name`, `service.instance.id` |
| HTTP | OTel | `http.request.method`, `http.route`, `http.response.status_code`, `server.address` |
| Messaging | OTel | `messaging.system`, `messaging.destination.name`, `messaging.operation.name`, `messaging.operation.type` |
| Database | OTel | `db.system.name`, `db.operation.name` |
| Errors | OTel | `error.type` — low-cardinality class or code, never a message |
| GenAI | OTel | `gen_ai.*` — the full set lives in `../tracing/genai/attributes.md` |
| Identity | OTel | `user.id`, `session.id` — subject to privacy policy, and never on metrics |
| Everything else | You | `app.*` |

High-cardinality values (`order.id`, `user.id`, `session.id`) are acceptable on spans when they have real diagnostic value and policy allows. They are never acceptable on metrics.

### The `app.*` shape

```
app.<domain>.<noun>              app.pricing.product_count
app.<domain>.<noun>.<qualifier>  app.retrieval.result_count
app.outcome                      one value from the closed set below
```

`app.outcome` values — the complete set; other files link here instead of
restating it:

| Value | Meaning |
| --- | --- |
| `success` | The unit finished and did its work; no `error.type` |
| `error` | The unit failed; span `ERROR` plus bounded `error.type` (`errors.md`) |
| `timeout` | The unit exceeded its deadline; also `ERROR` with `error.type=TimeoutError` (`errors.md#cancellation`) |
| `blocked` | A guardrail or policy refused the unit; a business result, not an exception |
| `cancelled` | Shutdown or client disconnect cancelled the unit; no `ERROR` (`errors.md#cancellation`) |
| `skipped` | The unit was deliberately not processed: duplicate, stale, or nothing to do |
| `hitl` | The unit was handed to a human; `ERROR` only when failure-driven (`errors.md#failures-visible-in-both-signals`) |

Keep the enum values for `app.outcome` fixed across the whole service. A metric that groups on it is only useful if the set is closed. Outcome is always `app.outcome` and classification always `error.type` (`errors.md`), on spans and app metrics alike: no `status`, `result`, or `error_code` synonyms. A business failure taxonomy is `app.failure.class`. Closed vocabularies are types, per the `python-code-conventions` skill (`../../../python-code-conventions/SKILL.md`, Closed vocabularies).

### The `app.*` registry

One fact gets one key. Four `app.*` domains for the same subject means four
dashboards that each miss three quarters of the data, so the domains are fixed:

| Domain | Owns | Examples |
| --- | --- | --- |
| `app.gen_ai.*` | model- and provider-level facts with no standard `gen_ai.*` equivalent | `app.gen_ai.usage.input_token_details`, `app.gen_ai.stream.chunk_count`, `app.gen_ai.input.capture_mode`, `app.gen_ai.output.capture_mode`, `app.gen_ai.input.batch_size`, `app.gen_ai.observation.input`, `app.gen_ai.observation.output`, `app.gen_ai.request.attempt`, `app.gen_ai.upstream_provider`, `app.gen_ai.estimated_cost_usd` |
| `app.agent.*` | facts about one agent **run**, not one model call | `app.agent.time_to_first_chunk`, `app.agent.step_count`, `app.agent.stop_reason`, `app.agent.fallback.used` |
| `app.workflow.*` | a durable or multi-step run | `app.workflow.name`, `app.workflow.run.id`, `app.workflow.version` |
| `app.job.*`, `app.worker.*`, `app.message.*` | scheduled, worker, and queue work | `app.job.type`, `app.worker.jobs`, `app.message.attempt` |
| `app.gen_ai.tool.*` | tool facts with no standard `gen_ai.tool.*` equivalent | `app.gen_ai.tool.requested_name`, `app.gen_ai.tool.result_size_bytes` |
| `app.retrieval.*`, `app.embedding.*`, `app.guardrail.*` | RAG and policy stages | `app.retrieval.result_count`, `app.guardrail.blocked` |
| `app.tenant.*`, `app.feature.*`, `app.experiment.*` | bounded request segmentation, including anything baggage propagates | `app.tenant.tier`, `app.feature.name`, `app.experiment.variant` |
| `app.telemetry.*` | bounded application-owned routing and projection facts; spans only | `app.telemetry.category="genai"` |
| `app.error.*` | logging-policy metadata; logs only, never exception content | `app.error.stacktrace_included`, `app.error.stacktrace_truncated` |
| `app.<business-domain>.*` | everything the service's own domain owns | `app.pricing.product_count`, `app.exception.rule` |
| `app.outcome`, `app.response.time_to_first_chunk` | deliberately flat, because they belong to no single domain | — |

Three rules follow from the table:

- **`app.llm.*` does not exist.** Model-adjacent facts live under
  `app.gen_ai.*`, mirroring the standard namespace they extend.
- **The tenant tier is `app.tenant.tier` everywhere** — span attribute, metric
  label, baggage key, and whatever a Collector transform maps it into. A second
  key for the same fact is not a namespace decision, it is a silent data split.
- **`app.telemetry.category="genai"` means that a span belongs to the rooted GenAI
  backend projection.** It does not turn an HTTP, job, or business span into a
  `gen_ai.operation`; never invent GenAI semantic attributes merely to retain a
  structural ancestor. Keep this marker off metrics and do not propagate it as
  baggage merely for Collector routing.

---

## Metric names and units

Metric names describe the measured thing; the instrument type describes how it is measured. Do not encode the instrument in the name.

| Good | Problematic |
| --- | --- |
| `app.pricing.updates` | `app.pricing.counter`, `app.pricing.updates.count` |
| `app.worker.job.duration` (unit `s`) | `app.worker.job.latency_ms` recorded in seconds |
| `app.retrieval.result_count` | `docs` |
| `app.exception.reviews` | `app.exception.reviews.count` |

**No `.count` suffix on an event counter.** A plural noun already says what is
being counted, the unit annotation (`{job}`, `{update}`) says it again, and
Prometheus appends `_total` on ingest — so `app.pricing.updates.count` arrives
as `app_pricing_updates_count_total`. `.count` is only correct when the *measured
quantity itself* is a count at a point in time, as in `app.retrieval.result_count`
(a histogram of "how many documents came back"), not the number of times
something happened.

Units are UCUM, and the unit is part of the name's contract: `s` for durations (never `ms`), `By` for bytes, and braced annotations such as `{request}` `{token}` `{document}` `{job}` for dimensionless counts. A name whose suffix disagrees with its unit — `latency_ms` recorded in seconds — misleads every reader and every alert.

*Which* instrument to reach for is a metrics-design question, not a naming one: `../metrics/service.md` has the table.

### Metric attributes are a hard boundary

Every unique attribute combination is a time series. Bounded values only:

```
allowed    service.name, deployment.environment.name, http.route, http.request.method,
           http.response.status_code, messaging.destination.name, messaging.operation.name,
           messaging.operation.type,
           gen_ai.operation.name, gen_ai.provider.name, gen_ai.request.model,
           gen_ai.response.model, gen_ai.tool.name (bounded), gen_ai.agent.name (bounded),
           app.job.type, app.outcome, app.tenant.tier, error.type (normalized)

forbidden  user.id, session.id, gen_ai.conversation.id, request_id, trace_id,
           order_id, document_id, gen_ai.response.id, raw URLs, exception messages,
           prompt or response text, tool arguments, app.telemetry.category, app.error.*
```

This is the list the metrics files defer to — `../metrics/service.md` and `../metrics/genai.md` add only the traps specific to their domain.

Trace IDs reach metrics through exemplars, never through labels.

Backends rename metrics. Prometheus turns `app.pricing.updates` into `app_pricing_updates_total` and `app.worker.job.duration` into `app_worker_job_duration_bucket`/`_count`/`_sum`. Verify the exported names in the backend before writing an alert against them.

---

## Log event names

Event-name style is owned by the `python-logging` skill
(`../../../python-logging/SKILL.md`). Here: a service's log event names come
from one enum, checked by a test against that style.

---

## Consistency across signals

The same fact should carry the same name everywhere it is bounded enough to appear:

```
span attribute   gen_ai.request.model = "gpt-5"
metric attribute gen_ai.request.model = "gpt-5"
log field        gen_ai.request.model = "gpt-5"
```

Metric labels use the same keys as span attributes. Where a log field must differ (conventionally flat), document the mapping once. Keep one short key and value-set table per service in the `observability/` module docstring rather than letting each call site improvise.

---

## Where names live in code

Span, metric and event names, and attribute keys shared across signals, emitters or tests, are constants in the conventions module (`../tracing/genai/attributes.md` for GenAI, `../setup/package_layout.md` for placement). Semconv keys may be literals. A log-only field key used by one module may be a literal. Keep the conventions module as the vocabulary, not a mirror of every key; review large modules for single-use entries. Constant naming in general: the `python-code-conventions` skill (Magic values and constants).
