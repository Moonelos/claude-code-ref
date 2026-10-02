# Production Tracing Policy

**Do not open this file unless the task involves production retention** —
sampling, filtering, telemetry cost, release burn-in, or an observability
rollout. It is retention policy, and absorbing it during ordinary
instrumentation work leads to proposing tail sampling for a dev service.

Design the retention and operational policy before writing Collector YAML. The
application records meaningful boundaries and exports vendor-neutral OTLP; the
Collector applies central filtering, redaction, sampling, routing, and bounded
export resilience.

## Contents

- [Retention contract](#retention-contract)
- [Required measurements](#required-measurements)
- [Head and tail sampling](#head-and-tail-sampling)
- [Deterministic noise](#deterministic-noise)
- [Capacity and cost](#capacity-and-cost)
- [Critical outcomes and diagnostics](#critical-outcomes-and-diagnostics)
- [Propagation and privacy](#propagation-and-privacy)
- [Rollout and ownership](#rollout-and-ownership)

---

## Retention contract

Start from value, not a universal percentage:

```text
failed traces                    -> keep 100%
slow traces                      -> keep 100%
critical or unusual outcomes     -> keep 100%
new-release burn-in              -> keep 100% temporarily
normal successful traces         -> keep a measured percentage
successful deterministic noise   -> suppress, drop, or sample very lightly
metrics                          -> never derive from sampled traces
logs                             -> retain independently by severity and policy
```

Define `slow`, `critical`, `high cost`, and `normal` for the named service.
Use full-fidelity metrics to measure rates and SLOs; traces provide retained
examples that explain those measurements. Important policies overlap, so
measure the actual effective retained ratio at the Collector instead of adding
configured percentages.

Low-volume critical routes may need 100% retention even when high-volume normal
traffic keeps much less. Stratify by bounded service, route template, workflow,
outcome, or release attributes; do not use raw IDs as policy dimensions.

---

## Required measurements

Collect the production inputs routed from `../discovery.md` before selecting
numbers. At minimum obtain new traces/second, average and p95 spans/trace, p99
complete-trace arrival, error/slow rates, serialized size, critical outcomes,
backend budget, and minimum useful daily samples.

If the data does not exist, keep the proposal provisional. Add the measurement
work and acceptance criteria; do not disguise example values as defaults.

---

## Head and tail sampling

Prefer 100% head recording in applications and value-based tail sampling in the
Collector. Tail sampling can retain errors, final latency, guardrail blocks,
fallbacks, high usage, and other outcomes learned only after work completes.
The error policy must retain a complete trace when **any** span has `ERROR`
status; do not implement it as a root-span-only attribute rule. Logs are sampled
and retained independently, so error log severity is not an input to this trace
decision. If a critical non-error outcome such as expected business HITL also
requires guaranteed retention, add a separate bounded outcome policy rather
than falsely marking it `ERROR`.

Use a parent-aware head sampler only when recording and transporting all spans
would itself endanger the service or Collector. State the trade-off explicitly:
tail sampling cannot recover an error trace the SDK never recorded.

For scaled tail sampling, route every span of a trace to the same stateful
sampler using trace-ID affinity. Ordinary round-robin fragments traces and
produces invalid decisions. Size `decision_wait` above p99 complete-trace
arrival plus export/network jitter, not merely application duration.

---

## Deterministic noise

Filtering and sampling solve different problems:

| Need | Mechanism |
| --- | --- |
| Never create a proven-useless span | SDK or instrumentation source exclusion |
| Centrally remove already-produced leaf/self-contained telemetry | Collector `filter` processor |
| Keep or drop a complete trace coherently | Tail-sampling policy |
| Retain representative useful traffic | Probabilistic policy |

Prefer source suppression only when the endpoint is trivial, failures remain
observable through metrics/logs or are intentionally not traced, and exclusion
does not remove required metrics. Verify that excluded handlers do not create
unrelated root spans through child instrumentations.

Collector filtering removes matching spans, not a complete trace. Restrict a
predicate by service, stable route, span kind, and outcome. Dropping a parent
can orphan children and correlated logs, so use a span filter only for verified
leaf or self-contained telemetry. Preserve failed probe traces whenever they
add diagnostic value; never let a broad probe-drop rule override error retention.

A destination-specific GenAI projection is the deliberate exception to the leaf-only rule, not
a retention policy. It may remove whole operational subtrees from only the GenAI backend after
the complete trace has made its sampling decision, provided the retained root, GenAI spans, and
meaningful business ancestors form an explicitly classified, ancestor-closed tree. The main
trace backend still receives the complete retained trace. See
`../collector/genai_projection.md`.

---

## Capacity and cost

Estimate retained volume before setting the percentage:

```text
daily retained spans
  ~= traces_per_second
     * average_spans_per_trace
     * 86,400
     * effective_retained_ratio

minimum active trace capacity
  ~= traces_per_second
     * decision_wait_seconds
     * burst_headroom
```

Use `../../scripts/estimate_trace_budget.py` for a deterministic first estimate.
Its output is a planning lower bound, not a memory-size prediction: serialized
bytes do not include all Collector in-memory overhead. Measure actual Collector
memory, early drops, late spans, decision latency, and effective retention under
load before rollout.

Configure sampled and non-sampled decision caches much larger than the active
trace buffer when late spans are possible. Bias cache capacity toward the more
common decision. Size exporter queues from measured batches and the outage
window worth buffering; persistent queues are bounded buffers, not a durable bus.

---

## Critical outcomes and diagnostics

Use bounded attributes that exist before the tail decision: route templates,
workflow names, service version, guardrail outcome, fallback use, step-limit
stop, bounded error type, or approved usage thresholds. Keep release burn-in
rules temporary and match immutable `service.version` values.

A forced diagnostic trace is an operational privilege. Accept it only from an
authenticated internal control with an allowlisted attribute, audit record,
expiry, owner, and automatic removal. Never trust a public request header,
queue field, or caller-supplied baggage value to force retention. Do not use a
raw tenant or user ID as a general sampling dimension; prefer a bounded tier or
cohort unless trace-only identity use has explicit privacy approval.

---

## Propagation and privacy

Set the deployment propagator explicitly to `tracecontext` by default. Add
`baggage` only after discovery identifies a small, bounded, non-sensitive value
that another service needs and `baggage.md` has been loaded. Trace
context already connects spans.

Sampling is never a privacy control. Minimize and mask content before telemetry
emission, apply Collector redaction before every trust boundary, and test canary
secrets in every destination. A rejected trace may still leave independently
retained correlated logs.

---

## Rollout and ownership

Record each policy's owner, rationale, thresholds, expected volume, start date,
review date, and expiry for temporary rules in version control.

Before rollout:

- validate the config against the exact pinned Collector image;
- exercise success, failure, slow, timeout, cancellation, retry, fallback, and shutdown;
- verify one complete golden trace in the main trace backend and the same trace ID as the
  configured connected projection in each specialized trace destination;
- run canary-secret and malformed-carrier tests;
- load-test SDK queues, sampling memory, decision caches, and exporters.

During rollout, canary the config, compare application request/job metrics with
Collector accepted/exported counts and backend ingest, and watch completeness,
orphans, late spans, early drops, errors retained, memory, and actual retained
percentage. Keep a tested rollback path.

Review the policy whenever traffic, routes, workflows, models, instrumentation,
or backend pricing changes. Remove release burn-in and force-sampling rules when
their expiry is reached.

---

## Operational levers that are not sampling

Three things belong to the same policy conversation and are often missed:

- **A kill switch.** `OTEL_SDK_DISABLED=true` turns off the SDK in one process
  without a code change. Decide during rollout whether operators may set it,
  who is allowed to, and how it is surfaced — an undocumented kill switch is
  found during an incident and never turned back on.
- **Log retention is a separate lever from trace sampling.** Traces are sampled
  by value at the Collector; logs are retained by severity. The default is keep
  `WARN`/`ERROR`, sample or drop high-volume `INFO`/`DEBUG` — and the mechanism
  is the log pipeline or the backend's own retention rules, not tail sampling
  (`../logging/correlation.md`).
- **Cost attribution needs an owner.** `app.gen_ai.estimated_cost_usd` is only
  as good as its price table. Decide where prices live, who updates them when a
  provider changes pricing, and how a historical figure is interpreted after a
  price change. An unversioned price table produces a cost dashboard that
  silently rewrites the past.

---

## Then

- Collector implementation of these decisions: `../collector/production.md`
- capacity arithmetic: `../../scripts/estimate_trace_budget.py`
- acceptance: `../collector/production.md`, Before calling it done
