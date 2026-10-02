# Production Collector Configuration

**Do not open this file unless a production Collector config is being
written or changed** (or, for staging, only the "Configuration" block that
`dev_staging.md` derives from). Read `../tracing/production_policy.md` first — it owns
the retention decisions this file implements, and implementing them without
the measurements it requires produces a config with unjustified numbers in it.

Production has a different job from staging: keep what explains failures, drop what costs money and teaches nothing, and never leak content into a backend that should not hold it.

## Contents

- [Sampling strategy](#what-a-production-tracing-strategy-preserves)
- [Deterministic noise](#remove-deterministic-noise-before-sampling)
- [Complete configuration](#configuration)
- [Processor order](#processor-order-is-not-cosmetic)
- [GenAI backend routing](#adding-a-genai-backend-path)
- [Redaction](#redaction-is-a-second-line-of-defence-not-the-first)
- [Scale and resilience](#tail-sampling-at-scale)
- [Deployment checklist](#before-calling-it-done)

---

## What a production tracing strategy preserves

```
all errors           → 100%
slow traces          → 100%
important traces     → 100%   (critical routes, high cost, guardrail blocks,
                                release burn-in, selected tenants)
normal successes     → a percentage
```

Retaining every trace forever is not a strategy — it is a bill. Retaining a flat 5% is not either: it drops most of your errors.

The exact rates depend on traffic volume, cost, latency thresholds, and operational requirements. Do not copy a percentage from this file without checking it against actual volume.

**Metrics are not sampled this way, in any environment.** They keep aggregating and exporting at full fidelity, because request counts, error rates, token totals, and SLO burn cannot be computed from a sample. No metrics pipeline — development, staging, or production — contains `tail_sampling`.

---

## Head sampling versus tail sampling

| | Decides | Can it keep all errors? |
| --- | --- | --- |
| Head (SDK) | at trace start | No — the error has not happened yet |
| Tail (Collector) | after the trace is assembled | Yes |

Use tail sampling for the policies above. Head sampling is only for crude volume reduction when even receiving every trace is too expensive; if you use it, use a parent-aware ratio sampler so whole traces are kept together.

---

## Remove deterministic noise before sampling

Read `../tracing/production_policy.md` first; it owns the decision between
source exclusion, span filtering, trace-aware sampling, and probabilistic
sampling. Prefer source exclusion for proven-useless work because it saves SDK,
network, and Collector cost. It also hides every status for that URL and may
suppress HTTP metrics, so verify both effects before enabling it.

Use the Collector filter only for a verified leaf or self-contained server span.
A span whose condition evaluates true is **dropped**.

The pinned Collector accepts two spellings, and **the path prefix rule differs
between them** — which is the actual trap here, because mixing them fails only
at startup:

| Key | Paths must be | |
| --- | --- | --- |
| `trace_conditions` | fully prefixed: `span.attributes[...]` | context-inference form; unprefixed `attributes[...]` is rejected |
| `traces: { span: [...] }` | either `span.attributes[...]` or bare `attributes[...]` | the long-standing per-signal, per-context form |

Do not reach for `trace_statements`: that is the *transform* processor's key and
it modifies telemetry rather than dropping it.

```yaml
processors:
  filter/successful_probes:
    error_mode: ignore
    trace_conditions:
      - >
        resource.attributes["service.name"] == "my-api" and
        IsMatch(span.attributes["http.route"],
                "^/(health|healthz|live|ready|metrics)$") and
        span.attributes["http.response.status_code"] == 200
```

Replace the service and routes with observed values. Keep the status predicate:
the rule above deliberately preserves failed probes. Never use only a global
span-name match. The filter removes individual matching spans, so dropping a
parent with instrumented children creates orphaned telemetry. If the endpoint
does real child work, retain or tail-sample the whole trace instead.

When enabled, insert this processor after resource enrichment and before
redaction/tail sampling. Validate the exact assembled config with
`otelcol validate` against the pinned image; a processor's schema is checked,
not assumed.

---

## Configuration

**Every value marked `# MEASURE:` below is a placeholder that happens to be
syntactically valid so the file can be image-validated. None of them is a
default.** Replace each one with the measurement named on its line before this
config reaches production; the inputs are collected in
`../tracing/production_policy.md`, "Required measurements". A config still
carrying the numbers below has not been sized — it has been pasted.

| Knob | Derive from |
| --- | --- |
| `decision_wait` | measured p99 complete-trace arrival + export/network jitter |
| `num_traces`, `expected_new_traces_per_sec` | measured new traces/second × `decision_wait` × burst headroom |
| `decision_cache` sizes | active capacity × late-span headroom, biased to the more common outcome |
| `latency.threshold_ms` | the service's own "slow" definition, above normal p95 |
| `numeric_attribute.min_value` | the token count that actually marks an expensive call here |
| `sampling_percentage` | measured volume, backend budget, and minimum useful daily samples |
| `memory_limiter.limit_mib` | the container memory limit, minus headroom |

```yaml
# services/otel-collector/config.prod.yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
  # Survives restarts with buffered telemetry. Needs a persistent volume.
  file_storage:
    directory: /var/lib/otelcol/storage
    create_directory: true

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  # First: the Collector must be able to shed load before the runtime kills it.
  # limit_mib must stay below the container memory limit.
  memory_limiter:
    check_interval: 1s
    limit_mib: 1024              # MEASURE: container memory limit minus headroom
    spike_limit_mib: 256

  resource/environment:
    attributes:
      - key: deployment.environment.name
        value: production
        # `insert` fills the gap for a sender that did not set it. `upsert`
        # would overwrite a correctly self-reporting service — a `uat`
        # deployment silently relabelled `production`, undetectable from the
        # application side. One owner per attribute: the application wins.
        action: insert

  # Universal secrets: removed on every path, including the GenAI branch.
  attributes/drop_secrets:
    actions:
      - key: http.request.header.authorization
        action: delete
      - key: http.request.header.cookie
        action: delete
      - key: http.response.header.set_cookie
        action: delete
      - key: db.query.text
        action: delete
      - key: db.statement
        action: delete
      - key: user.email
        action: delete

  # Exception detail on SPANS only. This skill's error contract forbids
  # first-party exception events, but auto-instrumentation still emits them.
  # Never apply this to the logs pipeline: the correlated log record is where
  # the stack trace is supposed to live (python-logging skill).
  attributes/drop_span_exception_detail:
    actions:
      - key: exception.message
        action: delete
      - key: exception.stacktrace
        action: delete

  # LLM payloads: removed on the general APM path only.
  attributes/drop_payloads:
    actions:
      - key: gen_ai.system_instructions
        action: delete
      - key: gen_ai.input.messages
        action: delete
      - key: gen_ai.output.messages
        action: delete
      - key: gen_ai.tool.definitions
        action: delete
      - key: gen_ai.tool.call.arguments
        action: delete
      - key: gen_ai.tool.call.result
        action: delete
      # Neutral backend-presentation copies are content too. They are mapped
      # only on the GenAI-backend branch and must not survive on the APM branch.
      - key: app.gen_ai.observation.input
        action: delete
      - key: app.gen_ai.observation.output
        action: delete

  tail_sampling:
    # Too short silently truncates traces; too long grows memory and delays
    # export. It must exceed p99 complete-trace ARRIVAL, not p99 duration.
    decision_wait: 30s           # MEASURE: p99 complete-trace arrival + jitter
    num_traces: 50000            # MEASURE: traces/s x decision_wait x burst
    expected_new_traces_per_sec: 500   # MEASURE: peak new traces/second
    # Keep late-span decisions much longer than active trace data; bias
    # capacity toward the more common keep/drop result.
    decision_cache:
      sampled_cache_size: 500000       # MEASURE: late-span decision headroom
      non_sampled_cache_size: 500000   # MEASURE: late-span decision headroom
    # Policies are evaluated as an OR: a trace is kept if ANY policy votes to
    # keep it. Only a `drop` policy vetoes; `not` inverts one policy's vote
    # (both present in 0.159.0, replacing the deprecated inverted decisions).
    # There is no "everything else" policy, so the probabilistic policy below
    # is evaluated against every trace. The
    # traces it selects that an earlier policy already kept are simply kept
    # once — which is why the net effect still is "errors/slow/important 100%,
    # normal successes at the configured percentage." It is also why configured
    # percentages cannot be summed to predict total retention.
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 15000    # MEASURE: this service's "slow", above normal p95

      - name: keep-provider-failures
        type: string_attribute
        string_attribute:
          key: error.type
          values: ["RateLimitError", "TimeoutError", "APIConnectionError"]

      - name: keep-high-token-traces
        type: numeric_attribute
        numeric_attribute:
          key: gen_ai.usage.input_tokens
          min_value: 8000        # MEASURE: token count that marks an expensive call here

      - name: keep-guardrail-blocks
        type: boolean_attribute
        boolean_attribute:
          key: app.guardrail.blocked
          value: true

      - name: sample-normal-successes
        type: probabilistic
        probabilistic:
          sampling_percentage: 5   # MEASURE: volume, backend budget, minimum useful samples

  batch:
    timeout: 5s
    send_batch_size: 1024

exporters:
  otlphttp/apm:
    endpoint: ${env:APM_ENDPOINT}
    headers:
      Authorization: ${env:APM_AUTHORIZATION}
    sending_queue:
      enabled: true
      queue_size: 10000
      storage: file_storage
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 10m

  otlphttp/metrics:
    endpoint: ${env:METRICS_ENDPOINT}
    headers:
      Authorization: ${env:METRICS_AUTHORIZATION}
    sending_queue:
      enabled: true
      queue_size: 10000
      storage: file_storage
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 10m

  otlphttp/logs:
    endpoint: ${env:LOGS_ENDPOINT}
    headers:
      Authorization: ${env:LOGS_AUTHORIZATION}
    sending_queue:
      enabled: true
      queue_size: 10000
      storage: file_storage
    retry_on_failure:
      enabled: true

service:
  extensions: [health_check, file_storage]
  telemetry:
    # Self-telemetry is a separate plane from the application telemetry below.
    # Use a different stable service.name for an agent or tail-sampling tier.
    resource:
      attributes:
        - name: service.name
          value: otel-collector-gateway
        - name: deployment.environment.name
          value: production
    # Collected from stderr by an independent platform log agent. Sending these
    # records into this Collector's own receiver couples them to its failures.
    logs:
      level: info
      encoding: json
    metrics:
      level: normal
      readers:
        - periodic:
            # Reader shutdown must leave time for application queues to drain.
            timeout: 5000
            exporter:
              otlp:
                protocol: http/protobuf
                endpoint: ${env:SELF_METRICS_ENDPOINT}
                headers:
                  Authorization: ${env:SELF_METRICS_AUTHORIZATION}
  pipelines:
    traces:
      receivers: [otlp]
      processors:
        - memory_limiter
        - resource/environment
        - attributes/drop_secrets
        - attributes/drop_span_exception_detail
        - attributes/drop_payloads
        - tail_sampling
        - batch
      exporters: [otlphttp/apm]

    # Metrics are NOT sampled. Full fidelity, always.
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, resource/environment, attributes/drop_secrets, batch]
      exporters: [otlphttp/metrics]

    logs:
      receivers: [otlp]
      # No drop_span_exception_detail here. The error contract moved exception
      # detail OUT of spans and INTO these records; deleting it here would
      # delete the only copy that exists.
      processors:
        - memory_limiter
        - resource/environment
        - attributes/drop_secrets
        - batch
      exporters: [otlphttp/logs]
```

The default metrics path is OTLP/HTTP. Use a backend-specific push exporter
only when the selected backend requires it; do not introduce a pull reader or
receiver as an intermediate transport.

### Processor order is not cosmetic

```
memory_limiter        first — self-protection before anything else
resource enrichment   before any rule that reads resource attributes
deterministic filter  optional; only for verified leaf/self-contained spans
redaction             before data crosses a trust boundary
tail_sampling         after the attributes its policies read exist
batch                 last, so exporters send efficient payloads
```

Redaction is also **per signal**: `attributes/drop_secrets` belongs on every
pipeline, `attributes/drop_span_exception_detail` on traces only, and
`attributes/drop_payloads` on the APM trace path only. A processor written for
spans and reused on logs is how a stack trace disappears from the one place the
error contract puts it.

Redaction after fan-out is redaction that already leaked. Tail sampling before enrichment cannot see the attributes it filters on.

Add a processor only with a stated purpose. Each one costs CPU and a place where telemetry can be silently altered.

---

## Adding a GenAI backend path

Two pipelines consume one application trace under the destination contract in `genai_projection.md`. This is how a GenAI-focused tracing tool receives only GenAI traces without a second SDK or trace.

```yaml
processors:
  filter/genai_projection:
    error_mode: ignore
    trace_conditions:
      # DROP unmarked spans; the application marks GenAI spans and their complete path to the root.
      - 'span.attributes["app.telemetry.category"] != "genai"'

exporters:
  otlphttp/genai:
    endpoint: ${env:GENAI_BACKEND_OTLP_ENDPOINT}
    headers:
      Authorization: ${env:GENAI_BACKEND_AUTHORIZATION}
    sending_queue:
      enabled: true
      queue_size: 10000
      storage: file_storage
    retry_on_failure:
      enabled: true

service:
  pipelines:
    traces/apm:
      receivers: [otlp]
      processors:
        - memory_limiter
        - resource/environment
        - attributes/drop_secrets
        - attributes/drop_span_exception_detail
        - attributes/drop_payloads     # APM does not get payloads
        - tail_sampling
        - batch
      exporters: [otlphttp/apm]

    traces/genai:
      receivers: [otlp]
      processors:
        - memory_limiter
        - resource/environment
        - attributes/drop_secrets      # secrets still go
        - attributes/drop_span_exception_detail
        - tail_sampling
        # Sample the complete trace before projecting; operational errors affect retention.
        - filter/genai_projection
        # Destination mapping processors go here (payloads stay on this branch);
        # see ../backends/<backend>.md.
        - batch
      exporters: [otlphttp/genai]
```

The filter does not infer ancestors; which spans to mark is in `genai_projection.md`, "The projection must be ancestor-closed".

**Naming `tail_sampling` in two pipelines allocates it twice.** This example has two buffers and decision-cache pairs. Budget `N ×` the single-instance estimate (`--sampling-pipelines N`), or sample once and fan out through a routing/forward connector. Identical probabilistic policies agree because both hash the same trace ID with the same default salt.

Destination mapping **copies** rather than renaming canonical `gen_ai.*`. Neutral `app.gen_ai.observation.*` values are deleted after the destination copies are made; APM contains neither payload representation. For Langfuse — exporter, authentication, and mapping processors — see `../backends/langfuse.md`.

---

## Redaction is a second line of defence, not the first

An `attributes` processor deletes **by key**. It cannot find a secret embedded inside an otherwise-permitted JSON string — an API key inside `gen_ai.input.messages`, an email inside a tool result.

Mask or allowlist content in the **application**, before it becomes a span attribute. Then use these rules to catch what the application missed.

Delete `user.email` by default. The Collector attributes processor's `hash`
action is unsalted SHA-1: it can obscure some high-entropy values, but it does
not anonymize a guessable email address and still creates a stable
cross-event identifier. If stable pseudonyms are a real business requirement,
create them before telemetry emission with a keyed HMAC, controlled key
rotation, documented retention, and privacy review.

Test it with canary values: put a fake API key, a fake email, and a fake authorization header through the pipeline and grep both backends' payloads for them. Do this whenever a new instrumentation library is added, because each one brings its own attribute keys.

---

## Tail sampling at scale

All spans of a trace must reach the same instance, or the sampler decides on a fragment and silently exports an incomplete trace.

```
services → trace-ID-aware load balancer → tail-sampling tier → backends
```

Standard round-robin breaks this. Use the `loadbalancing` exporter with `routing_key: traceID` in a front tier, or the Operator's equivalent.

Also watch: `decision_wait` must exceed p99 complete-trace arrival plus
SDK/export/network jitter. A 30-second agent trace under a 10-second
`decision_wait` gets decided on partial data.

Estimate a starting active buffer as:

```text
num_traces >= new_traces_per_second * decision_wait_seconds * burst_headroom
```

Use `../../scripts/estimate_trace_budget.py` to calculate a reproducible lower
bound, and pass `--sampling-pipelines N` when `tail_sampling` is named in more
than one pipeline. Serialized trace size is not Collector heap size, so
load-test and tune against real memory. Configure decision caches much larger
than `num_traces` when late spans are possible, and bias them toward the more
common sampled or non-sampled outcome.

Monitor traces dropped before decision, late spans, policy evaluation errors,
decision latency, memory-limiter activity, and the actual effective retained
ratio. Important policies overlap; configured percentages cannot be added to
predict the result.

### Temporary high-value policies

Add service-specific policies only after the matching bounded attributes have
been verified in exported spans:

```yaml
- name: keep-critical-routes
  type: string_attribute
  string_attribute:
    key: http.route
    values: ["/checkout", "/payments/{payment_id}"]

- name: keep-release-burn-in
  type: string_attribute
  string_attribute:
    key: service.version
    values: ["<immutable-new-release-git-sha>"]
```

Record an owner and expiry for release burn-in, then remove it automatically or
as a required rollout step. A force-sampling policy additionally requires an
authenticated internal producer, allowlisted attribute, audit record, and TTL;
never map a public request header or caller-supplied baggage directly to it.

---

## Resilience

| Setting | Prevents |
| --- | --- |
| `memory_limiter` first, below the container limit | OOM-kill instead of graceful shedding |
| `sending_queue` with `file_storage` | Losing buffered telemetry on restart |
| `retry_on_failure` with a bounded `max_elapsed_time` | Retrying forever into a dead backend |
| `batch` last | Inefficient per-span exports |

Size the queue from measured batch size and the outage you are willing to buffer through. A bigger queue costs memory and does not repair a slow backend. A persistent queue is a write-ahead log, not a durable message bus — it still loses data if the disk fills or the retry window expires.

Telemetry loss is preferable to application downtime. Silent telemetry loss during an incident is the worst of both, so alert on the Collector's own metrics (`component.md`).

---

## Deploy carefully

- Validate every config change in CI against the exact production image.
- Record the policy owner, rationale, thresholds, expected volume, review date, and expiry of temporary rules.
- Roll config changes gradually and keep a tested rollback path. A bad telemetry config creates blind spots precisely when you need visibility.
- Canary one bounded operation before rollout. Confirm that the APM backend has the complete tree
  without GenAI payloads and that the GenAI backend has the same trace ID as a connected
  root/business/GenAI projection with the expected captured-content mappings.
- Compare application request/job metrics with Collector accepted/exported counts and backend ingest; process health alone does not prove delivery.
- Watch trace completeness, orphan rate, late spans, early decisions, error-trace retention, memory, queue utilisation, and actual retained percentage during the canary.
- Remove release burn-in and forced-diagnostic rules when their expiry is reached.
- Keep environment credentials separate.

---

## Before calling it done

This is the acceptance checklist for a production Collector and for any
production retention or rollout change (`../tracing/production_policy.md` owns
the policy; `../verification.md` §10–11 point here).

Config and capacity:

- [ ] `otelcol validate` passes against the production image.
- [ ] No `# MEASURE:` value from this file survives unreplaced.
- [ ] The policy records measured new traces/second, average and p95 spans/trace,
      p99 complete-trace arrival, serialized size, backend budget, and minimum
      useful samples. Example percentages and capacities were not copied as defaults.
- [ ] `memory_limiter` is first, and its limit is below the container memory limit.
- [ ] No metrics pipeline contains a sampling processor.
- [ ] `decision_wait` exceeds measured **p99 complete-trace arrival plus jitter**, not merely p99 trace duration.
- [ ] `num_traces` and decision caches survive measured bursts and late spans, multiplied by the number of pipelines that name `tail_sampling`. Exercise a deliberately late span.
- [ ] Trace-ID-aware routing exists in front of any scaled tail-sampling tier.
- [ ] Collector telemetry shows no early drops, unexpected late spans, policy
      errors, or memory pressure at the expected peak. Record the actual effective
      retained ratio rather than adding configured policy percentages.

Retention behaviour:

- [ ] Force a failure and a slow operation: complete retained traces reach the
      main backend and specialized backends receive their same-trace-ID connected
      projections regardless of the normal-success percentage. The sampled
      percentage is justified by measured volume.
- [ ] Error retention matches any `ERROR` span and keeps the entire trace; log severity alone does not satisfy this check.
- [ ] Critical non-errors use a separate bounded-outcome policy instead of false `ERROR` status.
- [ ] Critical routes/outcomes are matched by bounded, observed attributes. Raw
      user, tenant, request, session, conversation, or workflow-run IDs are not
      general sampling dimensions.
- [ ] Successful-noise handling preserves failed probes and does not orphan
      instrumented children; a Collector span filter matches only a verified leaf
      or self-contained boundary.
- [ ] A release burn-in rule matches one immutable `service.version`, has an
      owner and expiry, and is removed in a rehearsal of the cleanup path.
- [ ] Any forced-diagnostic path is authenticated, internal, allowlisted,
      audited, time-bounded, and cannot be activated by public headers, messages, or
      caller-supplied baggage.
- [ ] Temporary burn-in/diagnostic rules have an owner and automatic or mandatory expiry removal.

Redaction and security:

- [ ] `deployment.environment.name` uses `action: insert`, so a service that sets its own environment is not relabelled.
- [ ] `exception.stacktrace` is deleted on traces only; the logs pipeline never
      overrides the application's exception-detail setting, and a canary
      exception's stack trace still arrives in the log backend.
- [ ] Canary secrets — a fake API key, email, and authorization header — reach no backend.
- [ ] `user.email` and other low-entropy personal fields are deleted on every
      Collector path; no test or documentation presents the unsalted `hash`
      action as anonymization.
- [ ] Credentials come from a secret store and appear in no committed file.
- [ ] Receivers are bound to private networks.

Delivery and self-telemetry:

- [ ] Receive and export counters both increase for a canary;
      `otelcol_exporter_send_failed_*` does not increase.
- [ ] Collector self-metrics are pushed over OTLP by a periodic reader to an
      independent monitoring path, with no pull reader or metrics listener, and
      the monitoring backend contains `otelcol_process_uptime`; structured
      internal logs leave via an independent platform log agent or direct endpoint.
- [ ] Any periodic self-metrics reader passes the reader-timeout and hanging-sink shutdown test in `component.md`, "Keep the monitoring path independent".
- [ ] Collector self-telemetry has stable role/environment identity, preserves
      the per-replica `service.instance.id`, and alerts use rates/increases for
      counters rather than historical values.
- [ ] Health probes, self-telemetry, and an end-to-end backend canary are all present; none is treated as proof supplied by another.
- [ ] One complete golden trace is searchable in the main backend and the same
      trace ID resolves to each expected specialized projection; reconcile
      application, Collector, and backend counts and document expected
      sampling/filtering differences.
- [ ] The config is canaried before fleet rollout and the rollback procedure is exercised.

GenAI backend (when configured):

- [ ] The projection passes `genai_projection.md`, "Acceptance invariants".
- [ ] Destination presentation attributes are created only on the GenAI-backend
      branch; the main trace backend contains neither `app.gen_ai.observation.*`
      nor any vendor payload copy such as `langfuse.observation.*`.
- [ ] Tail sampling evaluates the complete trace before the GenAI projection filter.
- [ ] Each GenAI-backend exporter passes that backend's checks in `../backends/` (Langfuse: `../backends/langfuse.md`).
