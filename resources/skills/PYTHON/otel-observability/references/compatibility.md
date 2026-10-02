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

Each choice below depends on the version set above; the rule itself is stated
once in the owner file. Re-check the owner when a version changes.

- Standard `gen_ai.client.token.usage` uses only `gen_ai.token.type=input|output`; subsets go to application-owned instruments: `metrics/genai.md`.
- `gen_ai.usage.cache_write.input_tokens` (not `cache_creation`), breakdowns only when reported with explicit zeros preserved, and audio per-modality attributes: `tracing/genai/token_usage.md`.
- Messaging spans follow the 1.44 schema (`messaging.operation.name` required and the span-name prefix, `messaging.operation.type` the bounded category, both set at span creation so head samplers can use them); the `boto3sqs` and Celery `0.65b0` instrumentors still declare legacy schema `1.11.0`, and Celery links only with code-based `use_span_links=True`: `tracing/queue_messaging.md`.
- LangChain `stream()` / `astream()` pass `version="v2"` and consume `StreamPart` dictionaries (`type`, `ns`, `data`), never the v1 tuple shape: `tracing/genai/langchain/streaming_and_agent_span.md`.
- Provider adapters promise no metadata casing or content-block representation; re-run provider fixtures and inspect installed adapter source on every adapter upgrade: `tracing/genai/langchain/model_callback.md`, "Compatibility gate".
- Lambda: community `/opt/otel-handler` versus the AWS-managed ADOT wrapper, layer ARNs unpinned (they vary by region, architecture, runtime, and release), and `xray-lambda` only for X-Ray export, never with `xray`: `tracing/lambda_functions.md`.
- Collector self-metrics use the declarative `service.telemetry.metrics.readers` periodic OTLP reader with a measured timeout (`5000` ms is the 30-second-budget example), internal logs `INFO` to `stderr`, internal traces opt-in: `collector/component.md`. On the pinned image the self-telemetry resource uses the declarative `resource.attributes` array; the legacy inline map is accepted only for backward compatibility and emits a warning.
- Langfuse receives complete traces or rooted, ancestor-closed projections (`collector/genai_projection.md`) over OTLP/HTTP with the v4 ingestion header and a configurable regional or self-hosted endpoint; readable input/output is a destination projection of content-gated `app.gen_ai.observation.*`, emitted only when a lossless presentation exists, while canonical `gen_ai.*` content stays the wire contract: `backends/langfuse.md`, `tracing/genai/content_capture.md`.

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
   resources, periodic readers, backend delivery, and alerts; re-run the
   periodic reader's hanging-sink shutdown test (`collector/component.md`, "Keep
   the monitoring path independent") and remeasure its timeout.
8. Confirm whether the `batch` **processor** is still the recommended batching mechanism at the candidate version, or whether exporter-level `sending_queue.batch` supersedes it. If batching moves into the exporter, the "`batch` last, after `tail_sampling`" ordering advice in `collector/production.md` changes with it.
9. Re-check every `gen_ai.*` attribute this skill uses against the pinned convention revision, not only the metric names. Resolve each changed key deliberately; never keep a key the pinned revision no longer defines.
10. Re-check backend authentication, endpoints, required headers, and whether trace ingestion remains real-time.
    Also send a text-only and a native structured-output canary and inspect the stored observation
    input/output, not only the raw span attributes; backend parsing and UI renderers evolve separately.
11. Run `otelcol validate` with the candidate image against every Collector config, run `python scripts/audit_telemetry.py` on the instrumented code, then perform the exported-telemetry checks in `verification.md`.

Record the new version set, convention tag or commit, and review date in this file in the same change.
