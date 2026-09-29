# Verification

Run this before reporting the work complete. Instrumentation fails silently by design — a missing span, a dropped attribute, and a broken exporter all look exactly like a quiet service.

Do not claim a step passed that you did not actually run. If something could not be exercised (no queue in the dev environment, no provider credentials), say so explicitly and name what remains unverified.

## Contents

- [See the telemetry](#1-see-the-telemetry)
- [Trace shape](#2-trace-shape)
- [Error handling](#3-error-handling)
- [Propagation](#4-propagation-multi-service-queue-or-durable-db-work)
- [AWS Lambda](#4b-aws-lambda-if-used)
- [GenAI spans](#5-genai-spans)
- [Content capture](#6-content-capture)
- [Metrics](#7-metrics)
- [Logs](#8-logs)
- [Configuration](#9-configuration)
- [Collector](#10-collector-if-deployed)
- [Production retention and rollout](#11-production-retention-and-rollout-if-production-or-sampling-changed)
- [Shutdown](#12-shutdown)
- [Focused tests](#13-focused-tests)
- [Report honestly](#report-honestly)

---

## 1. See the telemetry

Get eyes on the actual output before checking anything else. Two options:

**In-process console exporter** — fastest, no infrastructure:

```python
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

jsonl_exporter = ConsoleSpanExporter(
    # The default formatter pretty-prints one span across several lines.
    formatter=lambda span: span.to_json(indent=None) + "\n",
)
tracer_provider.add_span_processor(SimpleSpanProcessor(jsonl_exporter))
```

**Collector debug exporter** — proves the export path too. See `collector/dev_staging.md`.

Several checks below grep the exported spans, so send that output to a file you can search rather than watching it scroll past:

```bash
OTEL_SERVICE_NAME=myservice python -m myservice > captured_spans.json 2>&1
jq -c . captured_spans.json >/dev/null
```

The custom formatter makes the file JSON Lines: one complete JSON object per
line. The `jq` command is a required smoke check; do not run duplicate or
cardinality queries against a file it cannot parse. If the service also writes
non-JSON stdout, point the exporter at a dedicated file stream instead of
mixing records. Later checks refer to this file by that name.

Remove the console exporter before committing.

---

## 2. Trace shape

Exercise one representative operation end to end, then check the exported spans.

- [ ] The boundary shape is correct: one trace per HTTP request or bounded job/message/retry attempt, and no span/trace remains open around an unbounded worker loop.
- [ ] Every span has a low-cardinality name. No IDs, prompts, or user values.
- [ ] Child spans are actually **children**. Siblings where you expected nesting mean context was lost — usually at a raw-thread or non-propagating executor boundary; modern `asyncio.create_task()` and `asyncio.to_thread()` copy context.
- [ ] There is exactly one span per logical operation. Two means automatic and manual instrumentation both own the boundary.
- [ ] Span count is proportional to the work, and each custom span has useful bounded operation/outcome/decision/result attributes rather than copied payloads or generic implementation fields.
- [ ] `service.namespace`, `service.name`, `service.instance.id`, `service.version`, and `deployment.environment.name` appear on every span.
- [ ] Start two replicas and confirm their `service.instance.id` values differ while `service.namespace` and `service.name` remain identical.
- [ ] `service.instance.id` remains unchanged across several operations from one process; a value that changes per request destroys instance-level analysis.
- [ ] Production `service.version` is the immutable artifact version, not `unknown`, `latest`, a branch name, or a rollout label — normally the full Git commit SHA supplied by CI/build.
- [ ] Platform telemetry carries its native identity too: Kubernetes has `k8s.pod.uid`, containers have `container.id`, ECS has `aws.ecs.task.arn` plus container identity when available, and Lambda has `faas.name`, `faas.version`, `faas.instance`, `cloud.provider`, `cloud.platform=aws_lambda`, and `cloud.region`.

## 3. Error handling

Force a failure — a bad credential, an unreachable dependency, a deliberately raised exception.

- [ ] The span has `ERROR` status.
- [ ] `error.type` is set, and is a bounded class name or code — not a message.
- [ ] **No exception span event in first-party code.** Grep the service's own
  source, not the environment — auto-instrumentation will keep emitting
  exception events, and that is expected, not a failure of this check:

```bash
git grep -n "record_exception\|add_event" -- '*.py'
```

Expect zero hits in code this work added or touched.

- [ ] The exception appears **once** at the owning boundary; its detail projection is verified by the `python-logging` skill.
- [ ] When enabled, that stack trace survives the Collector and any explicit truncation is marked; deleting it on the logs path removes the only detailed copy the error contract leaves.
- [ ] A handled failure with a successful fallback does **not** mark the span `ERROR`.
- [ ] Terminal failure-driven HITL marks the owner `ERROR`, keeps `app.outcome=hitl`, and carries the bounded cause.
- [ ] Expected business HITL remains non-error and is distinguishable by status.
- [ ] An any-span `ERROR` filter finds the failure even with an unset root; its log carries the owning span's `trace_id`/`span_id`.
- [ ] Every `error.type` value is in the allowed set of `conventions/errors.md`; success omits it.
- [ ] `python scripts/audit_telemetry.py <src>` reports no findings in code this work added or touched.

## 4. Propagation (multi-service, queue, or durable DB work)

- [ ] Synchronous and explicitly continued boundaries share a `trace_id`.
  Linked asynchronous boundaries intentionally start a different trace.
- [ ] Client spans have matching server spans downstream.
- [ ] For a queue consumer, the exported shape matches the declared policy:

```
continued trace   consumer trace_id == producer trace_id, parent_span_id set
linked trace      consumer trace_id != producer trace_id, parent_span_id empty,
                  exactly one link with a valid producer SpanContext
```

- [ ] There is not both an automatic and a manual consumer span for one message.
- [ ] For SQS: `MessageAttributeNames` is requested on receive. Without it the fields never arrive and every consumer trace is an orphan.
- [ ] For a DB-backed worker/state machine, the work row stores a W3C carrier
  (`traceparent` plus optional `tracestate`), not only a trace ID or a
  serialized SDK context.
- [ ] The carrier and the work item/runnable state commit atomically in one DB
  transaction. Roll back either one and confirm neither becomes visible.
- [ ] The transition span is a new root with a link to the stored context; it
  is not a child of the worker's polling, `SELECT`, lease, or claim span.
- [ ] A retry of the same work item retains the original scheduling carrier and
  changes only its bounded attempt field. A successful next-state handoff
  persists a fresh carrier from the span that made that state runnable.
- [ ] Missing, malformed, and oversized stored carriers are ignored safely and
  produce an unlinked root; they do not fail or authorize the work.

## 4b. AWS Lambda (if used)

- [ ] Exactly one invocation span exists. A Lambda layer and a manual handler
  wrapper do not both own it.
- [ ] Invoke twice in one warm environment: provider construction happens once,
  both invocations export, and no per-invocation `shutdown()` runs.
- [ ] The exported invocation carries `faas.invocation_id` and
  `aws.lambda.invoked_arn`; API Gateway uses the configured route rather than a
  concrete path as the span name/`http.route`.
- [ ] For SQS, the batch and per-message shape matches the declared policy;
  independently failed messages have their own spans and partial-batch result.
- [ ] X-Ray export uses `xray-lambda` without `xray`. Non-X-Ray export does not
  use `xray-lambda`.
- [ ] A success, exception, near-timeout, and partial SQS batch all force-flush
  within the configured bound and their final telemetry arrives.
- [ ] The deployed instrumentation and Collector layers match the function's
  region, architecture, runtime, and pinned package line. No documentation or
  code hardcodes an obsolete layer ARN.
- [ ] `context.aws_request_id` is not `service.instance.id`; the full
  `AWS_LAMBDA_LOG_STREAM_NAME` is reused for `faas.instance` and
  `service.instance.id`, or a module-level fallback UUID stays stable across
  warm invocations.

## 5. GenAI spans

- [ ] One model span per **physical** model request, including each retry attempt.
- [ ] `gen_ai.request.model` is the real model name — and differs between the main and summarization models. A hardcoded name passes casual inspection and is wrong.
- [ ] Missing model identity omits `gen_ai.request.model` and names the span `chat`, without an invented model sentinel; it never records LangChain's `ls_model_type` values `chat` or `llm` as a model.
- [ ] `gen_ai.provider.name` and `gen_ai.operation.name` are set at span creation.
- [ ] `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` are non-zero.
- [ ] Cache read/write, reasoning, and audio breakdown attributes are present when the provider reports them, including an explicit `0`, and absent when unavailable. Cache writes use `gen_ai.usage.cache_write.input_tokens`, never the retired `cache_creation` spelling.
- [ ] `app.gen_ai.usage.input_token_details` / `output_token_details` are populated only when the provider reports details.
- [ ] Streaming: `gen_ai.response.time_to_first_chunk` is set, and is **smaller** than the span duration. If token attributes are absent on streamed calls only, the model was not configured to include usage in the stream.
- [ ] Streaming: `app.gen_ai.stream.chunk_count` is non-zero with content capture off and matches capture-on runs for the same fixture.
- [ ] Provider-returned `gen_ai.response.model` appears on both the span and model metric attributes when it differs from the request model.
- [ ] Agent runs: model and tool spans nest under `invoke_agent`, and `app.agent.time_to_first_chunk` is **larger** than the first model span's TTFC.
- [ ] Streaming: a span created by the **consumer** between two streamed chunks is a child of the request span, **not** of the model or agent span. If it nests under either, a wrapper is holding a span current across a `yield` (`tracing/genai/provider_sdk.md`).
- [ ] Streaming: the agent is invoked the way production invokes it — sync and async paths both produce model spans.
- [ ] Tool spans exist per attempt, not per logical call — force a transient tool failure and count them.
- [ ] Three turns of one conversation produce three traces sharing `gen_ai.conversation.id`, not one long trace.

## 6. Content capture

- [ ] With `CAPTURE_AI_CONTENT` unset or false, **no** payload attribute appears anywhere:

```bash
grep -E 'gen_ai\.(input\.messages|output\.messages|system_instructions|tool\.definitions|tool\.call\.(arguments|result))' captured_spans.json
```

Expect no matches.

- [ ] With it enabled, the attributes appear and hold the standard message-array schema.
- [ ] Raw spans keep canonical `gen_ai.*` role/parts envelopes. If a backend-native
  presentation is configured, text-only input additionally has role/content and one
  valid structured-output response additionally has the decoded JSON object under
  content-gated `app.gen_ai.observation.input` / `output`.
- [ ] A provider response containing one exactly empty reasoning part plus one JSON text part
  keeps both parts in canonical output but projects the decoded object for the backend. Repeat
  with non-empty reasoning and confirm the presentation falls back to the canonical envelope.
- [ ] On the GenAI-backend branch, the stored observation uses the backend's mapped
  input/output keys and the neutral source keys are absent from metadata (Langfuse:
  `backends/langfuse.md`, Verify). Expand or query the stored output and verify the actual
  content, since a collapsed object may display only an item count.
- [ ] If capture is filtered or truncated, `app.gen_ai.input.capture_mode` marks it.
- [ ] `gen_ai.conversation.compacted` is absent unless the model genuinely received compacted context.

## 7. Metrics

- [ ] Every selected default instrument for this app shape produces data, and each omitted baseline row has a documented reason. Export once and look:

Query the metrics backend for the canary service's `app.*`, `gen_ai.*`, and
`http.server.*` instruments. With no Collector, use an in-process
`ConsoleMetricExporter`; do not add a scrape endpoint only for verification.

- [ ] Counters and duration histograms increment on the **failure** path too. An error rate whose denominator excludes errors gets quieter as the service degrades.
- [ ] Histogram values land in real buckets, not all in `+Inf`. Default buckets are tuned for sub-second HTTP calls and are wrong for a 30-second LLM histogram.
- [ ] Exported boundaries include the configured GenAI/job values: client/tool/TTFC through `81.92`, agent through `409.6`, workflow/job through `7200`, fan-out through `128`, and token usage through `67108864`.
- [ ] Units are correct — seconds, not milliseconds, in an `s` histogram.
- [ ] `gen_ai.invoke_agent.inference_calls` records once per invocation, and its value equals the number of model spans in that trace.
- [ ] Standard `gen_ai.client.token.usage` has only `gen_ai.token.type=input|output`; cache and reasoning subsets appear only on application-owned breakdown histograms.
- [ ] An explicitly reported zero token or breakdown count is recorded as zero; a missing count produces no observation.
- [ ] Successful standard GenAI observations omit `error.type`; failures carry a bounded value.
- [ ] **No forbidden label.** This is the check that prevents an expensive backend incident:
  inspect the exported backend series and confirm no `user_id`, `session_id`,
  `conversation_id`, `trace_id`, `request_id`, or `response_id` label exists.

- [ ] Series count is flat under sustained load. Growth under steady traffic means a high-cardinality label slipped in.

## 8. Logs

- [ ] A log emitted inside a span carries a 32-hex `trace_id` and a 16-hex `span_id`.
- [ ] That trace ID finds the trace in the trace backend.
- [ ] With a GenAI projection, that trace ID finds the operation in both trace backends; a log from an omitted operational span is expected to have no observation-level `span_id` match there.
- [ ] For a linked worker/state-machine trace, logs carry the current worker
  trace ID, not the producer trace ID stored in the span link.
- [ ] Durable workflow boundary logs and transition spans share the documented
  `workflow_run_id` / `app.workflow.run.id` value; the ID appears on no metric.
- [ ] Event catalogue, redaction canary, and one-record-per-failure checks pass per the `python-logging` skill (`../../python-logging/references/testing-and-verification.md`).

## 9. Configuration

- [ ] Every new environment variable exists in the service's config object — not read via `os.environ` at a call site.
- [ ] Every new variable is declared in the deployment (compose file, Helm values, task definition, `.env.example`).
- [ ] Defaults are explicit: content capture off, exception detail at the safe projection in production YAML, no backend credentials in app containers; both detail settings are verified against a canary exception.
- [ ] `OTEL_SERVICE_NAME` and `SERVICE_NAMESPACE` are required repository-specific values. Missing either fails startup with a clear settings validation error; other new variables use their documented safe defaults.
- [ ] Exactly one owner sets each service resource attribute. Code-based setup does not duplicate the same keys in `OTEL_RESOURCE_ATTRIBUTES`; zero-code setup does not build an in-code provider.
- [ ] Collector enrichment cannot overwrite the application: `resource`/`attributes` processors use `action: insert`, `resourcedetection` uses `override: false`. Test it — send telemetry with `deployment.environment.name=uat` through the pipeline and confirm it arrives as `uat`, not as the Collector's value.
- [ ] Kubernetes receives instance identity through the Downward API or the existing service-attribute derivation owner; Compose resolves container identity inside the container; ECS queries both the current-container and `/task` Metadata v4 endpoints once before provider creation.
- [ ] A gateway Collector does not stamp application telemetry with the Collector's own pod, container, task, hostname, or IP.

## 10. Collector (if deployed)

- [ ] `otelcol validate` passes against the exact production image.
- [ ] Receive and export counters both increase; `otelcol_exporter_send_failed_*` stays at zero.
- [ ] Canary secrets — a fake API key, email, and authorization header — reach no backend.
- [ ] `user.email` is deleted on every Collector path. No test or documentation treats the Collector's unsalted hash action as anonymization.
- [ ] Exception detail is deleted on traces only. The logs pipeline preserves `exception.stacktrace` when present and never overrides the application's exception-detail setting.
- [ ] No metrics pipeline contains a sampling processor.
- [ ] No `# MEASURE:` placeholder value from `collector/production.md` survives in a deployed config.
- [ ] The main trace backend receives the complete retained operation tree and contains neither canonical verbose GenAI content nor destination presentation copies.
- [ ] The GenAI backend receives the same trace ID and only the rooted projection: entry root, GenAI workflow/agent/model/embedding/retrieval/tool spans, and meaningful business ancestors; unrelated operational siblings are absent.
- [ ] Every retained GenAI-projection span has its complete parent chain to the root; retained trace IDs, span IDs, parent IDs, status, and timestamps match the main backend.
- [ ] Business ancestors use `app.telemetry.category="genai"` only as projection membership; they do not carry a fabricated `gen_ai.operation.name`.
- [ ] The health endpoint responds — and remember it proves only that the process is up, not that the backend is accepting data.
- [ ] Collector self-metrics use a periodic OTLP reader with no pull reader or
  metrics listener; the monitoring backend contains `otelcol_process_uptime`.
- [ ] Each GenAI-backend exporter passes that backend's checks under `backends/` (Langfuse: `backends/langfuse.md`).
- [ ] Destination presentation attributes are created only on the GenAI-backend branch;
  general trace backends contain neither `app.gen_ai.observation.*` nor any vendor
  payload copy such as `langfuse.observation.*`.

## 11. Production retention and rollout (if production or sampling changed)

- [ ] The policy records measured new traces/second, average and p95 spans/trace,
  p99 complete-trace arrival, serialized size, backend budget, and minimum useful
  samples. Example percentages and capacities were not copied as defaults.
- [ ] Force a failure and a slow operation: complete retained traces reach the main backend and specialized backends receive their same-trace-ID connected projections regardless of the normal-success percentage.
- [ ] Error retention matches any `ERROR` span and keeps the entire trace; log severity alone does not satisfy this check.
- [ ] Critical non-errors use a separate bounded-outcome policy instead of false `ERROR` status.
- [ ] Critical routes/outcomes are matched by bounded, observed attributes. Raw
  user, tenant, request, session, conversation, or workflow-run IDs are not
  general sampling dimensions.
- [ ] A release burn-in rule matches one immutable `service.version`, has an
  owner and expiry, and is removed in a rehearsal of the cleanup path.
- [ ] Any forced-diagnostic path is authenticated, internal, allowlisted,
  audited, time-bounded, and cannot be activated by public headers, messages, or
  caller-supplied baggage.
- [ ] Successful noise and failed probes follow the declared policy. If a
  Collector span filter is used, the matched span is a verified leaf or
  self-contained boundary and no orphaned child spans appear.
- [ ] `decision_wait` exceeds measured p99 complete-trace arrival plus jitter;
  `num_traces` survives the measured burst; decision caches retain late-span
  decisions. Exercise a deliberately late span.
- [ ] Collector telemetry shows no early drops, unexpected late spans, policy
  errors, or memory pressure at the expected peak. Record the actual effective
  retained ratio rather than adding configured policy percentages.
- [ ] One complete golden trace is searchable in the main backend and the same trace ID resolves to each expected specialized projection; reconcile application, Collector, and backend counts and document expected sampling/filtering differences.
- [ ] The config is canaried before fleet rollout and the rollback procedure is
  exercised. Temporary burn-in and forced-diagnostic rules have automatic or
  mandatory expiry removal.

## 12. Shutdown

- [ ] A CLI job or worker exits and its final spans still arrive. Run once, then look in the backend — this is the most commonly missed step, and it fails silently.
- [ ] If the Collector pushes self-metrics with a periodic reader, its
  reader-level timeout is explicit, measured, and comfortably below the
  platform termination grace period, leaving budget for application exporter
  queues to drain.
- [ ] Stop that Collector while the self-metrics destination accepts a TCP
  connection but never responds. It exits before the platform deadline and
  queued application telemetry still drains. Do not substitute an invalid
  hostname: fast DNS failure does not exercise the hanging-export path. Record
  the exit code separately; a failed final self-metrics export may still exit
  non-zero even when the timeout bound works.
- [ ] A Lambda invocation force-flushes within its remaining-time budget but
  keeps providers alive for a warm reuse.
- [ ] A cancelled or disconnected streaming request still ends its spans.
- [ ] Under a pre-fork server, spans appear from every worker process, not just one.

## 13. Focused tests

When the repository already has a test suite, run focused tests for deterministic
helpers and lifecycle paths in addition to the exported-telemetry checks:

- normal completion, provider/tool exception, and handled fallback;
- capture on and off, empty stream, error after first chunk, partial stream,
  cancellation, and abandoned generator;
- propagation extraction/injection, invalid/oversized carriers, atomic DB
  handoff, retry carrier retention, and explicit empty-context roots;
- serializers with batched input, multiple generations, multimodal parts, and
  tool calls;
- GenAI projection marking on a mixed tree: one marked root, every marked in-trace parent marked, meaningful business ancestors retained, and operational siblings unmarked;
- redaction canaries and duplicate automatic/manual boundary ownership.

Do not add a new test framework only for observability. State which paths were
not executable in the current environment.

---

## Report honestly

State what you verified and how, what you could not verify and why, and any assumption you made during discovery that the user should confirm.

If a check failed and you could not fix it, say so plainly with the observed output. A partial implementation reported accurately is useful; a complete-sounding report over unverified instrumentation costs someone an incident.
