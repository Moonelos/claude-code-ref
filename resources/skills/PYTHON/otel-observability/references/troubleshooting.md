# Troubleshooting: Symptom → Cause → File

Start here when the task is "something is wrong with the telemetry" rather than
"add telemetry". Find the row, load the **one** file it names, and stop. Do not
run the greenfield intake in `discovery.md` for a one-line fix.

Two things first, because they explain a surprising share of reports:

1. **Look at exported telemetry, not at the code or an in-memory object.**
   `verification.md` §1 sets up a console exporter and a greppable capture file
   in about a minute. A conclusion drawn from reading the instrumentation code is
   a guess.
2. **Instrumentation fails silently by design.** A missing span, a dropped
   attribute, a dead exporter, and a healthy quiet service look identical. The
   absence of an error message is not evidence.

---

## Nothing arrives

| Symptom | Likely cause | File |
| --- | --- | --- |
| No spans anywhere, no errors | No provider configured, or `opentelemetry-instrument` and in-code setup both ran and one won | `setup/sdk_bootstrap.md` |
| Spans appear locally, nothing in the backend | Exporter endpoint or protocol mismatch; `404` from appending `/v1/traces` to a per-signal variable, or gRPC/HTTP port confusion | `setup/package_layout.md`, "The OTLP/HTTP path trap" |
| A CLI job or scheduled run produces nothing | Process exited before the batch processor flushed | `tracing/scheduled_jobs.md` |
| Spans from only one worker process | Provider built before the fork | `setup/startup_prefork.md` |
| Metrics missing but traces fine | No metric reader, or export interval longer than the test run | `setup/sdk_bootstrap.md` |
| Metrics appear in the debug exporter but not in the backend | Metrics OTLP endpoint, protocol, authentication, or Collector exporter routing is wrong | `collector/dev_staging.md` |

## Too much arrives

| Symptom | Likely cause | File |
| --- | --- | --- |
| Two spans for one request, job, or message | Two owners of one boundary — auto-instrumentation plus a manual span | `setup/auto_instrumentation.md` |
| Two consumer spans per queue message | `boto3sqs` instrumentation is active *and* a manual consumer span exists | `tracing/queue_messaging.md` |
| Doubled token counts and cost | Two generation-capture paths: this skill's callback plus a Langfuse `CallbackHandler`, OpenInference, or a LiteLLM gateway | `tracing/genai/langchain/architecture.md`, "Do not double-instrument" |
| Forty spans for a health check | An instrumentation package is too chatty — usually `botocore` or `urllib3` | `setup/auto_instrumentation.md` |
| Trace size grows with rows or candidates and database scopes dominate | ORM or driver instrumentation emits connection and statement spans for every physical operation; the retained boundary may be too low-level for the current operational goal | `setup/high_volume_database_tracing.md` |
| Metric series count grows under steady traffic | A high-cardinality label slipped in | `conventions/naming.md` |

## The trace has the wrong shape

| Symptom | Likely cause | File |
| --- | --- | --- |
| Spans are siblings where you expected nesting | Context lost at a thread pool, executor, or independently scheduled task | `tracing/worker_runtime.md` |
| …and the code streams | A span was held current across a `yield`, so the consumer inherited it | `tracing/genai/provider_sdk.md`, "Why the span is never current across a `yield`" |
| Consumer trace is an orphan — no parent, no link | SQS attributes were not requested on receive; `MessageAttributeNames` for W3C, `MessageSystemAttributeNames` for `AWSTraceHeader` | `tracing/queue_messaging.md` |
| Consumer shares the producer's trace ID when it should be linked | `context=None` (or omitted) means "use the current context", not "start a root" | `tracing/async_handoffs.md` |
| Work hangs off the poller's `SELECT` span | The DB claim span was used as the parent instead of the stored carrier | `tracing/durable_work.md` |
| A streaming span never ends | The generator was abandoned, so its `finally` never ran | `tracing/genai/provider_sdk.md` |
| Model spans stay open after a cancelled agent run | The callback's abandoned-run guard is not called from the wrapper's `finally` | `tracing/genai/langchain/model_callback.md` |
| Whole conversation is one endless trace | One trace per turn, correlated by `gen_ai.conversation.id` — not one per conversation | `tracing/genai/attributes.md` |
| Production traces are truncated or missing late spans | `decision_wait` shorter than p99 complete-trace **arrival** | `collector/production.md` |

## GenAI values are wrong or missing

| Symptom | Likely cause | File |
| --- | --- | --- |
| Token attributes absent on streamed calls only | Usage not requested: `stream_usage=True` on the model, or `stream_options={"include_usage": True}` on the SDK call | `tracing/genai/token_usage.md` |
| `gen_ai.request.model` is `chat` or `llm` | `ls_model_type` used as a model-name fallback; omit the attribute instead | `tracing/genai/langchain/model_callback.md` |
| Every call reports the same model | Hardcoded model name; the summarization model exposes it | `tracing/genai/langchain/model_callback.md` |
| No model spans at all from a LangChain agent | Handler/invocation style mismatch (`AsyncCallbackHandler` with `invoke`), or the callback was attached at invoke time only | `tracing/genai/langchain/model_callback.md`, "Sync versus async invocation" |
| `gen_ai.invoke_agent.inference_calls` never appears | One of the three counter wiring edits is missing; the failure is silent | `metrics/genai.md`, "Counting fan-out per invocation" |
| Agent TTFC equals model TTFC | Agent TTFC was computed from `"updates"`, which is step-granular | `tracing/genai/langchain/streaming_and_agent_span.md` |
| Prompts present with `CAPTURE_AI_CONTENT` unset | A capture path is not gated on the setting | `tracing/genai/content_capture.md` |
| Structured JSON appears as an expandable object inside a text part in Langfuse | Often correct: Langfuse parsed a JSON string for display. Inspect the raw exported `gen_ai.output.messages` before changing the serializer | `tracing/genai/content_capture.md`, "Backend rendering is not the wire shape" |
| `finish_reason` is `unknown`, system instructions are duplicated, or provider content blocks are empty | The callback assumed generic field names instead of the locked provider adapter's actual metadata and request conversion | `tracing/genai/langchain/model_callback.md`, "Compatibility gate" |
| No embedding or retrieval spans in a RAG service | Nothing instruments the retriever automatically; those spans are hand-written | `tracing/genai/retrieval.md` |

## Resource identity is wrong

| Symptom | Likely cause | File |
| --- | --- | --- |
| Replicas share one `service.instance.id` | Instance ID derived from a static value — service name, replica ordinal, image tag | `setup/resource_identity.md` + the runtime file |
| `service.instance.id` changes per request | It is being generated per call instead of per process | `setup/resource_identity.md` |
| All telemetry carries the Collector's pod or task ID | A gateway detector enriched from its own runtime | `setup/resource_identity.md` |
| `service.version` is `unknown` in production | CI did not inject the Git SHA into the image | `setup/resource_identity.md` |
| A `uat` deployment shows as `production` | Collector `resource` processor used `action: upsert` and overwrote the application | `collector/production.md` |

## Logs and metrics

| Symptom | Likely cause | File |
| --- | --- | --- |
| Log records have no `trace_id` | Emitted outside any span, or the trace-context processor runs after the renderer | `logging/correlation.md` |
| `trace_id` absent only on logs from a background task, thread, or executor, while the request's own logs have it | Context was lost when the work was scheduled; the enricher writes IDs only for a valid span context, so the field is missing rather than zero | `tracing/worker_runtime.md` |
| Worker logs carry the producer's trace ID | The linked producer context was copied into the log's `trace_id` | `logging/correlation.md` |
| Logs reference a trace the backend does not have | Normal: tail sampling drops traces, not logs | `logging/correlation.md`, "Trace sampling does not sample logs" |
| Exception has no stack trace in the log backend | The Collector's logs pipeline deletes `exception.stacktrace` | `collector/production.md` |
| The exception log record is missing entirely, not just its stack trace | Backend structured-metadata size limit rejected the whole record; the traceback attribute exceeded it | `python-logging` skill (`../../python-logging/references/errors-and-security.md`, "Record-size limits") |
| One incident, six stack traces | Logging at every call depth instead of at the owning boundary | `conventions/errors.md` |
| Every histogram value in `+Inf` | Default buckets are sub-second; the instrument was created without `explicit_bucket_boundaries_advisory` (a `View` is only for third-party instruments) | `metrics/service.md`, "Instruments and units" |
| Error rate falls as the service degrades | The metric is recorded only on the success path | `metrics/service.md` |
| The metric name is not in Prometheus | Backends rename on ingest: `_total`, `_bucket`, `_count`, `_sum` | `conventions/naming.md` |

## Collector

| Symptom | Likely cause | File |
| --- | --- | --- |
| Collector refuses to start | A component or key that does not exist in the pinned image — validate the exact config against the exact image | `collector/component.md` |
| `401` from Langfuse | The base64 auth string carries a trailing newline | `backends/langfuse.md`, "Exporter and authentication" |
| Langfuse shows orphaned model leaves or no request/job root | A retained GenAI span's root or parent chain was not marked with `app.telemetry.category="genai"`; the span filter does not infer ancestors | `collector/genai_projection.md` |
| Langfuse contains database, HTTP-client, or persistence noise | The GenAI projection filter is missing, or operational siblings were marked as projection members | `collector/genai_projection.md` |
| The main trace backend contains prompts, outputs, or duplicated presentation payloads | The main branch does not delete canonical verbose content and `app.gen_ai.observation.*` / `langfuse.observation.*` copies | `collector/production.md` |
| Retained percentage does not match the configured one | Tail-sampling policies OR together and overlap; measure the effective ratio | `collector/production.md` |
| Sampler memory twice the estimate | `tail_sampling` named in two pipelines is two processor instances | `collector/production.md` |
| Export counters flat while receive counters climb | Backend rejecting or credentials wrong; watch `otelcol_exporter_send_failed_*` | `collector/component.md` |
| `docker stop` stalls near the grace period, or exits `1` only when the self-metrics backend is impaired | A periodic self-metrics reader is attempting its final export with a missing or oversized reader timeout | `collector/component.md`, "Keep the monitoring path independent" |

---

## If no row matches

Then it is not a known failure mode, and the next step is evidence rather than
another guess:

1. capture exported spans to a file (`verification.md` §1);
2. narrow to one operation and one signal;
3. state what you expected, what arrived, and the smallest difference between
   them.

Report that rather than changing configuration speculatively. A telemetry change
made on a guess produces a second, harder problem.
