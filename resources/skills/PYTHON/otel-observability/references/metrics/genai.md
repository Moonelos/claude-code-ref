# GenAI and Agent Metrics

These sit **on top of** the service metrics in `service.md`, not instead of them. An agent service still needs request rate, error rate, latency, and queue health.

---

## Default suggested GenAI baseline

Start with the two **core** rows for every model-calling application, then add
each conditional row whose capability exists. These sit on top of the matching
service baseline in `service.md`. Use the standard names rather than inventing
`llm.requests`, so dashboards, backends, and future instrumentation agree.

The Stability column is taken from the pinned convention revision
(`../compatibility.md`): it defines no stable GenAI metric, so every `gen_ai.*`
row is **development**; `app.*` rows are app-defined.
Before adding a `gen_ai.*` row, confirm the pinned revision defines that name;
if it does not, emit it as `app.gen_ai.*` instead.

| Default when | Metric | Instrument | Unit | Stability | Answers |
| --- | --- | --- | --- | --- | --- |
| Every GenAI app | `gen_ai.client.operation.duration` | Histogram | `s` | development | model latency, error rate, timeouts |
| Every GenAI app | `gen_ai.client.token.usage` | Histogram | `{token}` | development | token distribution and prompt growth |
| Streaming | `gen_ai.client.operation.time_to_first_chunk` | Histogram | `s` | development | streaming UX |
| Tool use | `gen_ai.execute_tool.duration` | Histogram | `s` | development | tool latency and error rate |
| Agent | `gen_ai.invoke_agent.duration` | Histogram | `s` | development | one agent invocation |
| Agent | `gen_ai.invoke_agent.inference_calls` | Histogram | `{inference_call}` | development | model fan-out per invocation |
| Agent with tools | `gen_ai.invoke_agent.tool_calls` | Histogram | `{tool_call}` | development | tool fan-out per invocation |
| Streaming agent | `app.agent.time_to_first_chunk` | Histogram | `s` | app-defined | end-user agent response latency |
| Multi-agent workflow | `gen_ai.invoke_workflow.duration` | Histogram | `s` | development | multi-agent workflow latency |

The two `*_calls` metrics are **histograms recorded once per invocation**, not counters incremented per call. They describe fan-out. Do not sum them against a per-call counter; the aggregation semantics differ and the result is meaningless.
Add `app.*` metrics only for product facts these do not express.

---

## The metrics module

Put these in the service's existing metrics module. A recorder function earns
its place only when an instrument is recorded from two or more call sites or
needs normalization, as the ones below do; otherwise record at the call site.
This is what the code in `../tracing/genai/langchain/` and
`../tracing/genai/provider_sdk.md` imports.

```python
# observability/metrics.py (GenAI section)
from collections.abc import Mapping

from opentelemetry import metrics

meter = metrics.get_meter(__name__)

# GenAI semantic-convention boundaries, pinned by ../compatibility.md.
CLIENT_DURATION_BUCKETS = [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]
TOKEN_BUCKETS = [float(4**i) for i in range(14)]  # 1 .. 67108864
AGENT_DURATION_BUCKETS = [0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4, 12.8, 25.6, 51.2, 102.4, 204.8, 409.6]
WORKFLOW_DURATION_BUCKETS = [1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0, 7200.0]
FAN_OUT_BUCKETS = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0]

model_duration = meter.create_histogram(
    "gen_ai.client.operation.duration",
    unit="s",
    description="Duration of one GenAI client operation.",
    explicit_bucket_boundaries_advisory=CLIENT_DURATION_BUCKETS,
)
token_usage = meter.create_histogram(
    "gen_ai.client.token.usage",
    unit="{token}",
    description="Tokens used by a GenAI client operation.",
    explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
)
# Cache and reasoning counts are subsets of input/output totals. Keep them on
# separate application-owned instruments so summing the standard histogram can
# never double-count usage or cost.
cache_read_token_usage = meter.create_histogram(
    "app.gen_ai.client.token.cache_read.usage",
    unit="{token}",
    description="Input tokens served from a provider cache.",
    explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
)
cache_write_token_usage = meter.create_histogram(
    "app.gen_ai.client.token.cache_write.usage",
    unit="{token}",
    description="Input tokens written to a provider cache.",
    explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
)
reasoning_token_usage = meter.create_histogram(
    "app.gen_ai.client.token.reasoning.usage",
    unit="{token}",
    description="Output tokens used for provider-reported reasoning.",
    explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
)
time_to_first_chunk = meter.create_histogram(
    "gen_ai.client.operation.time_to_first_chunk",
    unit="s",
    description="Time from request to first streamed chunk.",
    explicit_bucket_boundaries_advisory=CLIENT_DURATION_BUCKETS,
)
tool_duration = meter.create_histogram(
    "gen_ai.execute_tool.duration",
    unit="s",
    description="Duration of one tool execution.",
    explicit_bucket_boundaries_advisory=CLIENT_DURATION_BUCKETS,
)
agent_duration = meter.create_histogram(
    "gen_ai.invoke_agent.duration",
    unit="s",
    description="Duration of one agent invocation.",
    explicit_bucket_boundaries_advisory=AGENT_DURATION_BUCKETS,
)
agent_inference_calls = meter.create_histogram(
    "gen_ai.invoke_agent.inference_calls",
    unit="{inference_call}",
    description="Model calls made during one agent invocation.",
    explicit_bucket_boundaries_advisory=FAN_OUT_BUCKETS,
)
agent_tool_calls = meter.create_histogram(
    "gen_ai.invoke_agent.tool_calls",
    unit="{tool_call}",
    description="Tool calls made during one agent invocation.",
    explicit_bucket_boundaries_advisory=FAN_OUT_BUCKETS,
)
workflow_duration = meter.create_histogram(
    "gen_ai.invoke_workflow.duration",
    unit="s",
    description="Duration of one coordinated GenAI workflow.",
    explicit_bucket_boundaries_advisory=WORKFLOW_DURATION_BUCKETS,
)
agent_ttfc = meter.create_histogram(
    "app.agent.time_to_first_chunk",
    unit="s",
    description="Agent invocation to first chunk visible to the caller.",
    explicit_bucket_boundaries_advisory=AGENT_DURATION_BUCKETS,
)


def record_model_operation(
    *,
    duration_s: float,
    operation: str,
    provider: str,
    request_model: str | None,
    response_model: str | None = None,
    usage: Mapping[str, object] | None = None,
    error_type: str | None = None,
) -> None:
    """Record duration and token usage for one physical model request."""
    attributes = {
        "gen_ai.operation.name": operation,
        "gen_ai.provider.name": provider,
    }
    if request_model:
        attributes["gen_ai.request.model"] = request_model
    if response_model:
        attributes["gen_ai.response.model"] = response_model

    # Recorded on the error path too, or the error rate has a denominator
    # that excludes errors.
    duration_attributes = dict(attributes)
    if error_type:
        # Standard GenAI metrics require error.type only on failures. Do not
        # add an application success sentinel to a standard instrument.
        duration_attributes["error.type"] = error_type
    model_duration.record(duration_s, duration_attributes)

    if not usage:
        return

    # Same normalized dict the span attributes are written from, so the two
    # can never disagree. Shape and adapters: ../tracing/genai/token_usage.md
    from observability.genai_usage import normalize_usage

    normalized = normalize_usage(usage)
    # These are the complete standard enum: input and output totals only.
    # Provider cache and reasoning values are normally subsets of those totals.
    for token_type, value in (
        ("input", normalized["input_tokens"]),
        ("output", normalized["output_tokens"]),
    ):
        # Preserve an explicit zero; only absence suppresses an observation.
        if value is not None:
            token_usage.record(
                value, {**attributes, "gen_ai.token.type": token_type}
            )

    for instrument, value in (
        (cache_read_token_usage, normalized["cache_read_tokens"]),
        (cache_write_token_usage, normalized["cache_write_tokens"]),
        (reasoning_token_usage, normalized["reasoning_tokens"]),
    ):
        if value is not None:
            instrument.record(value, attributes)


def record_time_to_first_chunk(
    duration_s: float, *, operation: str, provider: str, request_model: str | None
) -> None:
    attributes = {
        "gen_ai.operation.name": operation,
        "gen_ai.provider.name": provider,
    }
    if request_model:
        attributes["gen_ai.request.model"] = request_model
    time_to_first_chunk.record(duration_s, attributes)


def record_tool_execution(
    *,
    duration_s: float,
    tool_name: str,
    error_type: str | None = None,
    agent_name: str | None = None,
    tool_type: str | None = None,
) -> None:
    # These are the attributes declared for gen_ai.execute_tool.duration.
    # gen_ai.operation.name belongs on the span, not on this metric.
    attributes = {"gen_ai.tool.name": tool_name}
    if agent_name:
        attributes["gen_ai.agent.name"] = agent_name
    if tool_type:
        # Standard values: function, extension, datastore.
        attributes["gen_ai.tool.type"] = tool_type
    if error_type:
        attributes["error.type"] = error_type
    tool_duration.record(duration_s, attributes)


def record_agent_invocation(
    *,
    duration_s: float,
    agent_name: str,
    error_type: str | None = None,
    inference_calls: int | None = None,
    tool_calls: int | None = None,
) -> None:
    # Agent duration and fan-out instruments do not declare
    # gen_ai.operation.name as a metric attribute.
    attributes = {"gen_ai.agent.name": agent_name}
    duration_attributes = dict(attributes)
    if error_type:
        duration_attributes["error.type"] = error_type
    agent_duration.record(duration_s, duration_attributes)
    # Recorded once per invocation — these are fan-out distributions.
    if inference_calls is not None:
        agent_inference_calls.record(inference_calls, attributes)
    if tool_calls is not None:
        agent_tool_calls.record(tool_calls, attributes)


def record_agent_time_to_first_chunk(duration_s: float, *, agent_name: str) -> None:
    agent_ttfc.record(duration_s, {"gen_ai.agent.name": agent_name})


def record_workflow_invocation(
    *, duration_s: float, workflow_name: str, error_type: str | None = None
) -> None:
    attributes = {"gen_ai.workflow.name": workflow_name}
    if error_type:
        attributes["error.type"] = error_type
    workflow_duration.record(duration_s, attributes)
```

`gen_ai.token.type` has exactly two standard values: `input` and `output`. Never extend that enum with cache or reasoning categories. The application-owned breakdown histograms preserve those provider-neutral subsets without making the standard total unsafe to aggregate.

Metric attribute sets are per instrument, not a global bag of valid GenAI
keys. In particular, keep `gen_ai.operation.name` on model metrics and spans;
do not add it to `gen_ai.execute_tool.duration`, the agent duration/fan-out
metrics, or the workflow duration metric unless a later pinned revision
declares it there.

Declare each histogram's boundaries at creation with
`explicit_bucket_boundaries_advisory` (`service.md`); the central `View`
registry in `../setup/sdk_bootstrap.md` is only for third-party instruments.

---

## Counting fan-out per invocation

`inference_calls` and `tool_calls` need a counter that lives for exactly one invocation. Use a context-scoped accumulator that the callback and tool middleware increment and the agent wrapper reads.

<!-- complete-python-template -->
```python
# observability/agent_counters.py (or the existing metrics module)
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class InvocationCounters:
    inference_calls: int = 0
    tool_calls: int = 0


_counters: ContextVar[InvocationCounters | None] = ContextVar(
    "invocation_counters", default=None
)


@contextmanager
def bind_counters(counters: InvocationCounters) -> Iterator[InvocationCounters]:
    """Make an existing counters object current for this scope.

    Streaming wrappers need this: their counters must outlive one resumption
    of a generator, but must not stay current across a `yield`. See
    ../tracing/genai/langchain/streaming_and_agent_span.md.
    """
    token = _counters.set(counters)
    try:
        yield counters
    finally:
        _counters.reset(token)


@contextmanager
def invocation_counters() -> Iterator[InvocationCounters]:
    """One fresh counter scope per agent invocation."""
    with bind_counters(InvocationCounters()) as counters:
        yield counters


def current_counters() -> InvocationCounters | None:
    return _counters.get()
```

Three call sites wire it up, and **all three are required** — with any one missing, `gen_ai.invoke_agent.inference_calls` and `.tool_calls` are simply never emitted, silently. Each already does so in its template: `on_chat_model_start` in the model callback (`../../assets/langchain/model_callback.py`) increments `inference_calls`; the tool tracing middleware (`../tracing/genai/langchain/tools_and_middleware.md`) increments `tool_calls`; the agent wrappers (`../tracing/genai/langchain/streaming_and_agent_span.md`) open the scope and pass both values to `record_agent_invocation`.

The increments are guarded on `current_counters()` returning non-`None` so a model call made outside any agent invocation — a standalone summarization, a warm-up call — does not raise inside instrumentation.

A `ContextVar` is the right container because it is per-task: two concurrent agent invocations in one process get independent counters, which a module-level integer would not.

---

## Why fan-out metrics matter more than they look

Latency and error rate can both stay flat while the agent silently gets worse:

```
previous release   2 model calls / invocation
new release        7 model calls / invocation
```

Same success rate, same p95, 3.5× the cost. The causes are reasoning loops, a prompt regression, a tool-selection regression, or a tool whose results the model no longer trusts. Nothing but a fan-out metric surfaces it.

Watch the same way:

```
tool calls per invocation       unnecessary or repeated tool executions
retries per invocation          provider or tool instability
tokens per invocation           prompt growth, retrieval bloat
summarization calls / invocation context growing beyond the trigger
```

Only tool calls per invocation has an instrument above (`gen_ai.invoke_agent.tool_calls`).
The other three are trace queries by default: retries are repeated `chat` or `execute_tool`
spans under one `invoke_agent` span, tokens are the `gen_ai.usage.*` sum over its model spans,
and summarization calls are `chat` spans for the summarization model (distinguishable by
`gen_ai.request.model`). When one needs a dashboard or alert, add an `app.agent.*` per-invocation
histogram and wire it exactly like `inference_calls`: a field on `InvocationCounters`, an
increment at the one call site that sees the event, and one observation in
`record_agent_invocation`. Never add a counter field with no increment and no instrument.

Alert on a change from baseline, not an absolute threshold — "7 model calls" is fine for one agent and pathological for another.

---

## Metrics worth adding beyond the standard set

Only where a product fact has no standard equivalent:

| Metric | Instrument | For |
| --- | --- | --- |
| `app.agent.step_limit.stops` | Counter | Runs stopped by max-step protection |
| `app.agent.fallback.activations` | Counter | Model or workflow fallback activations |
| `app.agent.cancellations` | Counter | User or system cancellations |
| `app.retrieval.result_count` | Histogram | Empty-retrieval detection |
| `app.guardrail.decisions` | Counter, by bounded decision + policy | Safety and policy trends |
| `app.gen_ai.estimated_cost_usd` | Histogram | Spend by workflow, model, tenant tier |

The cache-read, cache-write, and reasoning token-subset histograms are already in
[the metrics module](#the-metrics-module), separate from the standard totals.

Do not add `app.agent.tool_calls` as a counter alongside `gen_ai.invoke_agent.tool_calls` unless you specifically need an event-rate view as well as a per-invocation distribution — and if you do, document that they are not interchangeable.

---

## Cardinality: the two GenAI-specific traps

The general lists are in `../conventions/naming.md`. Two things are specific to GenAI and catch people who have read them:

- **Tool and agent names are model-supplied.** They are bounded only if you bound them. Normalize against a known registry before the name reaches a metric attribute — see `../tracing/genai/langchain/tools_and_middleware.md`. Model and provider names need no such treatment; they come from your own configuration.
- **`gen_ai.response.id` is unique per call.** It sits in the same attribute group as `gen_ai.response.model`, reads like metadata, and behaves like a UUID. It belongs on the span and nowhere near a label.

`gen_ai.conversation.id` is the third one, and the most expensive: one time series per conversation. The rule is in `../tracing/genai/attributes.md`, "Conversation correlation".

---

## Cost and quality are separate from health

Low latency and a low error rate do not mean the answers are correct. Quality needs its own signals — evaluator scores, user feedback, guardrail outcomes — and those usually live in an LLM observability backend rather than the metrics backend.

Split the responsibility:

```
metrics backend   latency, errors, tokens, fan-out, cost proxies, alerts
Langfuse or eval  prompts, outputs, scores, datasets, quality analytics
```

If quality scores are exported as metrics, publish the sample count next to every average. A 0.62 groundedness score over four samples is noise, and paging on it trains people to ignore the page.

---

## Verify

- One `gen_ai.client.operation.duration` observation per **physical** model request, including retries.
- The standard token histogram has only `input` and `output`; their sum matches provider totals without cache or reasoning double-counting. Explicit zero observations survive, while unavailable token types produce no observation.
- Cache-read, cache-write, and reasoning subsets appear only on the three application-owned breakdown histograms.
- Forcing a provider error still produces a duration observation, with `error.type` set.
- Successful standard GenAI measurements omit `error.type` rather than using a success sentinel.
- `gen_ai.invoke_agent.inference_calls` records once per invocation, and its value matches the number of model spans in that trace.
- No metric carries a conversation ID, user ID, or response ID.
- Series count stays flat under sustained load.

---

## Then

- logging: the `python-logging` skill (`../../../python-logging/references/genai.md`), with `../logging/correlation.md`
- final checks: `../verification.md`
