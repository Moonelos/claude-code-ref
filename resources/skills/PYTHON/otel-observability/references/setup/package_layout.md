# Package Layout and Configuration

Where the observability code lives, and how its settings reach it.

---

## Follow the project, don't impose a layout

Look at what the service already has and extend it. Two shapes are common and both are fine:

**A small service with an existing `core/` package:**

```
core/
    config.py            <- existing; add the telemetry settings here
    logging.py           <- existing logging owner (python-logging skill)
    observability.py     <- new; SDK bootstrap
```

**A service large enough that telemetry deserves a package:**

```
observability/
    __init__.py          <- exports configure_observability / shutdown_observability
    tracing.py           <- Resource, TracerProvider, span processors, propagators
    metrics.py           <- MeterProvider, readers, instrument definitions
    logging.py           <- add_otel_trace_context (../logging/correlation.md)
    spans.py             <- start_span, mark_error, error_type_of
    genai.py             <- model callbacks, tool middleware, agent wrappers  }
    genai_attributes.py  <- GenAI convention constants                        } GenAI
    genai_usage.py       <- token usage normalization                         } only
    genai_content.py     <- message/payload serializers                      }
    agent_counters.py    <- fan-out counters, if not in metrics.py           }
```

Pick the second when the service has GenAI instrumentation, more than one boundary type, or business metrics — those three together outgrow a single module quickly. GenAI instruments go in the existing `metrics.py`; split instruments by capability only once that module holds roughly fifteen.

---

## What belongs in the service observability package

Within one service, "shared package" below means its common observability
module. For repeated operational contracts or a library across deployables,
read `shared_library.md`; it adds the reuse threshold, dependency boundary,
explicit lifecycle, shared-logging contract, and consumer-by-consumer migration
rules.
With a workspace library, generic plumbing belongs there; vocabulary and adapters stay local. The service maps resolved settings to explicit library inputs, which never load environment variables, YAML, or secrets.
The package owns all code whose sole purpose is telemetry, including:

- the `Resource`
- `TracerProvider` and `MeterProvider` (no OTel `LoggerProvider`; logs leave
  through the python-logging sink)
- exporters and span/metric processors
- propagator configuration
- SDK initialization and shutdown, or the managed-runtime force-flush lifecycle
- shared helper functions — a `set_usage_attributes()`, a stable cross-service
  outcome enum when one genuinely exists, or a duration-measuring context manager
- framework-specific telemetry adapters such as LangChain model callbacks,
  tool-tracing middleware, usage parsers, and agent-invocation wrappers

---

## Keep setup and adapters in separate modules

A LangChain callback handler, a `@wrap_tool_call` middleware, or an OpenAI
response parser does **not** belong in the module that builds the
`TracerProvider`; placement (`observability/genai.py` beside a
framework-free `tracing.py`, in the tree above) is owned by
`../../../python-service-architecture/references/ai.md` (Middleware and
observability).

Keep `observability/__init__.py` narrow so non-GenAI entry points do not eagerly
load `observability.genai`. A module inside a package does not make every package
consumer depend on its imports unless the package initializer or a common import
path eagerly re-exports it.

Do not create `agents/observability/`, `genai/observability/`, or another nested
package merely because an adapter imports LangChain. Split only for a large,
independently changing collection, distinct lifecycle/test setup, or demonstrated
import pressure. One callback plus one tool middleware stays flat.

---

## Configuration

**Every environment variable this work introduces goes into the service's existing configuration mechanism** — usually `config.py` or `settings.py`. Instrumentation code reads the settings object, not `os.environ`.

This matters because config objects are where a service already does validation, defaults, type coercion, and documentation. A `os.getenv("CAPTURE_AI_CONTENT")` buried in a callback is untyped, untested, and invisible to anyone reading the config.

Declare each field per the `python-settings-config` skill
(`../../../python-settings-config/SKILL.md`): which values are required, which
live in YAML (including exception detail), and which are OPTIONAL diagnostic
switches with a safe Python default (content capture, export intervals). Preserve the
service's existing settings shape. Nothing reads settings at import time;
bootstrap maps them to explicit telemetry and logging inputs.

### Variables you will typically add

| Variable | Purpose | Default |
| --- | --- | --- |
| `OTEL_SERVICE_NAME` | Logical service identity. Required. | none — fail loudly |
| `SERVICE_NAMESPACE` | System/application grouping. Required. | none — fail loudly |
| `SERVICE_VERSION` | Immutable build identity; prefer the full Git commit SHA | none — required; the build fails when the SHA is empty (`resource_identity.md`, Version policy) |
| `SERVICE_INSTANCE_ID` | Runtime instance identity; platform-supplied when possible | UUID v4 per process |
| `ENVIRONMENT` | Becomes `deployment.environment.name` | `development` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Base OTLP endpoint | `http://localhost:4318` |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Per-signal override | derived from base |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Per-signal override | derived from base |
| `OTEL_BSP_MAX_QUEUE_SIZE` | Maximum queued spans waiting for export | `2048` |
| `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` | Maximum spans in one export batch | `512` |
| `OTEL_BSP_SCHEDULE_DELAY` | Delay between scheduled span exports, in milliseconds | `5000` |
| `OTEL_BSP_EXPORT_TIMEOUT` | Span batch export timeout, in milliseconds | `30000` |
| `OTEL_METRIC_EXPORT_INTERVAL` | Interval between metric exports, in milliseconds | `15000` |
| `OTEL_METRIC_EXPORT_TIMEOUT` | Metric export timeout, in milliseconds | `30000` |
| `OTEL_PROPAGATORS` | Set explicitly in deployment; add baggage only when routed by `SKILL.md` | `tracecontext` |
| `CAPTURE_AI_CONTENT` | GenAI content capture switch | `false` |
| `LOG_LEVEL` | Log level, owned by the python-logging pipeline | `INFO` |

Sampling configuration follows the provider owner and the policy selected in
discovery. For a code-owned provider, pass `ALWAYS_ON` directly for Collector
tail sampling; for head sampling, add a validated ratio to the existing settings
object and construct the parent-aware sampler shown in `sdk_bootstrap.md`. Do
not also add `OTEL_TRACES_SAMPLER` variables to a code-owned provider. For
zero-code setup, use `OTEL_TRACES_SAMPLER=always_on` for Collector tail sampling
or `parentbased_traceidratio` plus `OTEL_TRACES_SAMPLER_ARG` for head sampling.

Resolve namespace and version ownership using `resource_identity.md`, then
resolve instance ownership using only the runtime reference selected by
`SKILL.md`. In particular, do not replace the `SERVICE_INSTANCE_ID` fallback
with a pod name, Compose service name, ECS service name, Lambda request ID, or
static replica ordinal.

### The OTLP/HTTP path trap

The base and per-signal endpoint variables behave differently, and this is the most common cause of a `404` with no other symptom:

| Setting | Behaviour |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318` | treated as a base; `/v1/traces` etc. are appended |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://collector:4318/v1/traces` | used exactly as given |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://collector:4318` | posts to `/`, which is not an OTLP endpoint — `404` |

Never append `/v1/traces` to an OTLP/**gRPC** target; gRPC dials `http://collector:4317` and calls a protobuf method.

---

## Wire it into the deployment

Add the new variables wherever the service's environment is declared — `docker-compose.yaml`, the Helm values file, the task definition, `.env.example`. A settings field with no deployment entry is a field that only works on the author's machine.

Keep credentials out of the application entirely when a Collector is in use: the application knows one internal OTLP endpoint and nothing about Langfuse, Datadog, or Prometheus keys.
