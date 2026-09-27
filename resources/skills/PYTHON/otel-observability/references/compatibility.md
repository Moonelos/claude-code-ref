# Compatibility Contract

Read this before copying version-sensitive examples. The GenAI conventions, LangChain stream shapes, Collector component schemas, and backend ingestion requirements evolve independently.

## Reviewed version set

Review date: **2026-09-02**. Review by: **2027-03-02**.

Past the review-by date, treat every version-sensitive example here as unverified and say so in your report: a stale contract is a prompt to re-check, not a broken package.

| Surface | Contract used by this skill |
| --- | --- |
| OpenTelemetry Python | `opentelemetry-api`, `opentelemetry-sdk`, and OTLP exporters `>=1.44,<1.45`; instrumentation packages from the matching `0.65b0` line |
| AWS Lambda instrumentation | `opentelemetry-instrumentation-aws-lambda==0.65b0`; this line adds SQS context propagation, while the AWS Lambda semantic conventions remain development-status |
| Resource semantic conventions | OpenTelemetry semantic conventions `1.44.0`; service identity is stable, platform resource conventions are at the status stated there |
| GenAI semantic conventions | Dedicated `open-telemetry/semantic-conventions-genai` repository at commit `eaefa142a94cefe5d199d47e4a73727dfbd825df` (2026-08-21) |
| LangChain | `>=1.3,<1.4`; examples were reviewed against `1.3.18` and `langchain-core 1.6.1` |
| LangChain AWS | Bedrock Converse examples were reviewed against `langchain-aws 1.7.4`; its response metadata preserves the provider's camel-case `stopReason`, and its request conversion moves `SystemMessage` content into Bedrock's top-level `system` field |
| LangGraph | `>=1.2,<1.3`; examples were reviewed against `1.2.11` and use the v2 `StreamPart` schema |
| Collector | Contrib distribution `otel/opentelemetry-collector-contrib:0.159.0` |
| Langfuse | OTLP/HTTP ingestion v4; send `x-langfuse-ingestion-version: "4"` |

These are compatibility bounds for the templates, not a demand to downgrade a service that already uses newer packages. When the repository has a locked version outside a range, adapt the example to that version and run the upgrade checks below.

## Deliberate compatibility choices

- Standard `gen_ai.client.token.usage` observations use only `gen_ai.token.type=input` and `output`. Cache and reasoning subsets use application-owned instruments.
- The standard cache-write span attribute is `gen_ai.usage.cache_write.input_tokens`; `cache_creation` remains only as a raw provider/LangChain field accepted by the adapter. Usage-breakdown attributes are emitted only when reported — an explicit zero is preserved, but an unavailable split is not fabricated as zero. Audio input/output details are projected to their standard per-modality attributes.
- Messaging spans follow the 1.44 schema: `messaging.operation.name` is
  required and supplies the span-name prefix (`send pricing-jobs`, `process
  pricing-jobs`); `messaging.operation.type` carries the bounded operation
  category. Record both at span creation so head samplers can use them. The
  `boto3sqs==0.65b0` automatic instrumentor adds SQS propagation but still
  emits its legacy `1.11.0` messaging schema; use the manual boundary when
  1.44-compliant messaging telemetry is required. The Celery instrumentor on
  the same line also declares schema `1.11.0`; it uses a producer parent by
  default and switches to a new task trace with a link only when code-based
  activation passes `use_span_links=True`.
- LangChain `stream()` and `astream()` examples pass `version="v2"` and consume `StreamPart` dictionaries with `type`, `ns`, and `data`. Do not mix them with the v1 tuple shape.
- LangChain provider adapters do not promise one metadata casing or content-block representation.
  Re-run provider fixtures and inspect installed adapter source on every adapter upgrade.
- Lambda examples distinguish the community `/opt/otel-handler` wrapper from
  the AWS-managed ADOT wrapper used by the selected layer. Layer ARNs are not
  pinned here because they vary by region, architecture, runtime, and release.
- Use `xray-lambda` only when Lambda spans export to AWS X-Ray. Do not combine
  it with the ordinary `xray` propagator, and do not use it for a non-X-Ray
  trace backend.
- Collector self-metrics use the declarative
  `service.telemetry.metrics.readers` schema with a periodic OTLP reader; pull
  readers are outside this skill's transport contract. The self-telemetry
  resource uses the declarative `resource.attributes` array —
  the legacy inline map is accepted only for backward compatibility and emits
  a warning. Internal logs remain at `INFO` and go to `stderr`; internal traces
  are experimental and opt-in. Periodic OTLP readers pin a measured timeout;
  `5000` ms is the reviewed 30-second-budget example, not a universal value.
- Langfuse receives either complete traces or rooted, ancestor-closed GenAI projections over
  OTLP/HTTP with the v4 ingestion header. A projected trace retains the application root and every
  parent of every retained span; the pinned Collector's span filter does not infer those ancestors.
  The endpoint remains configurable for region and self-hosting.
- Langfuse-readable input/output is a destination projection, not the portable wire contract:
  keep `gen_ai.system_instructions` / `gen_ai.input.messages` / `gen_ai.output.messages`
  canonical, emit content-gated `app.gen_ai.observation.input` / `output` only when a
  lossless presentation is available, and map those to `langfuse.observation.input` /
  `output` in the Langfuse Collector branch.

## Upgrade checklist

Before changing any version above:

1. Re-check every standard metric name, attribute name, enum value, requirement level, and recommended histogram boundary against the pinned GenAI conventions.
2. Re-check service-instance uniqueness, deployment environment values, and Kubernetes/container/cloud resource attributes against the pinned resource conventions. Re-check messaging span names plus the requirement levels and values of `messaging.operation.name` and `messaging.operation.type`.
3. Re-check Lambda invocation attributes, API Gateway/SQS trigger semantics,
   `xray-lambda` rules, wrapper path, layer compatibility, and end-of-invocation
   force-flush behaviour against the selected instrumentation release.
4. Run capture-on and capture-off streaming tests against the real LangChain/LangGraph stream shape. Cover an empty stream, cancellation, and an error after the first chunk.
5. Re-run model/provider metadata fixtures so `gen_ai.request.model` can never become a model type such as `chat` or `llm`; verify finish-reason casing, system-field ownership, structured-output type, and provider content blocks at the same time.
6. Validate **every** Collector YAML block under `references/collector/` with the exact candidate image and inspect its `components` output for renamed or removed components.
7. Re-check internal-telemetry schema, stability, names, logs, traces,
   resources, periodic readers, backend delivery, and alerts. For a
   periodic reader, stop against a hanging — not DNS-failing — sink and remeasure
   its timeout and total shutdown against the platform grace period.
8. Confirm whether the `batch` **processor** is still the recommended batching mechanism at the candidate version, or whether exporter-level `sending_queue.batch` supersedes it. If batching moves into the exporter, the "`batch` last, after `tail_sampling`" ordering advice in `collector/production.md` changes with it.
9. Re-check every `gen_ai.*` attribute this skill uses against the pinned convention revision, not only the metric names. Resolve each changed key deliberately; never keep a key the pinned revision no longer defines.
10. Re-check backend authentication, endpoints, required headers, and whether trace ingestion remains real-time.
    Also send a text-only and a native structured-output canary and inspect the stored observation
    input/output, not only the raw span attributes; backend parsing and UI renderers evolve separately.
11. Run `otelcol validate` with the candidate image against every Collector config, run `python scripts/audit_telemetry.py` on the instrumented code, then perform the exported-telemetry checks in `verification.md`.

Record the new version set, convention tag or commit, and review date in this file in the same change.
