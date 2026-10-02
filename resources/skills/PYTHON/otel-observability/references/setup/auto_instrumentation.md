# Auto-Instrumentation: What to Install, What to Leave Off

Auto-instrumentation gives you the boundaries a framework already knows about — HTTP server, HTTP client, database, cache. It cannot know your business operations. In particular, SQL instrumentation can see an `INSERT`, `UPDATE`, or `SELECT`, but cannot know that a row schedules or resumes durable work; that handoff needs the explicit boundary in `../tracing/durable_work.md`. Dependency and business instrumentation answer different questions. Retain each layer only when its incident value justifies its volume; neither automatically substitutes for the other.

Evaluate the package set **per service**. A worker and an API in the same repo should not automatically get the same list.

---

## Choose by what the service actually does

Install an instrumentation package only when the service uses that library in a path worth observing. **Installed** means the instrumentor is available; it does not patch anything by itself in code-based setup. **Activated** means an explicit `.instrument()`/`.instrument_app()` call ran, or the zero-code launcher loaded the package's entry point.

| The service… | Install |
| --- | --- |
| serves HTTP with FastAPI | `opentelemetry-instrumentation-fastapi` |
| calls HTTP with httpx / requests | `opentelemetry-instrumentation-httpx` / `-requests` |
| uses SQLAlchemy / psycopg / asyncpg | `opentelemetry-instrumentation-sqlalchemy` / `-psycopg` / `-asyncpg` |
| uses Redis | `opentelemetry-instrumentation-redis` |
| runs Celery tasks | `opentelemetry-instrumentation-celery` — **it owns the publish and task spans**; do not also write your own. Its `0.65b0` parent-vs-link option and legacy schema are in `../tracing/queue_messaging.md`, "Other brokers". |
| runs as an AWS Lambda function | `opentelemetry-instrumentation-aws-lambda`, normally supplied by one selected Lambda instrumentation layer |
| needs trace IDs in stdlib `logging` records or direct OTel export of them | `opentelemetry-instrumentation-logging` — its `0.65b0` export-handler default and when to set `OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION=false`: `../logging/correlation.md`, "`LoggingInstrumentor`" |

Plus the SDK and exporter:

```bash
pip install opentelemetry-api opentelemetry-sdk \
  opentelemetry-exporter-otlp-proto-http
```

Use the HTTP exporter for a Collector listening on `4318`, the gRPC exporter (`opentelemetry-exporter-otlp-proto-grpc`) for `4317`. Note that Langfuse ingestion accepts OTLP/HTTP only — if the Collector forwards to Langfuse, that constraint lives at the Collector's exporter, not here.

In code-based setup, the package stays inert until its activation owner calls
`.instrument()` or `.instrument_app()`. In zero-code setup,
`opentelemetry-instrument` discovers installed entry points and activates them
before the application imports. Installing packages "just in case" therefore
widens what zero-code mode may patch and obscures ownership even if a code-based
process never activates them.

---

## What to deliberately leave off

### High-volume database and ORM tracing

Database instrumentation is optional when its physical connection and statement spans overwhelm the
business trace. Before enabling, retaining, disabling, or replacing it for a high-volume workload,
read [high_volume_database_tracing.md](high_volume_database_tracing.md). It owns the evidence test,
replacement contract, diagnostic-mode option, logging requirements, and verification checks. Do not
replace noisy automatic spans with equally noisy manual repository spans or per-query logs.

**Low-level AWS SDK tracing.** `opentelemetry-instrumentation-botocore` spans every `botocore` API call. In a service that lists objects, reads parameters, and refreshes credentials, that is thousands of spans that explain nothing, and it drowns the handful of spans that do. Leave it off unless a specific AWS call is a latency or failure suspect.

Same reasoning for:

| Package | Leave off unless |
| --- | --- |
| `botocore` | you need a specific AWS operation observed |
| `boto3sqs` | you want the library's queue semantics instead of your own — **or** you need its carrier adapters, which is a different case, resolved below |
| `urllib3` | you are not already tracing at the `requests`/`httpx` layer — otherwise it double-reports every outbound call |
| `system-metrics` | the host/container platform is not already reporting CPU, memory, and process metrics |
| `sqlite3` | the local database is genuinely a performance question |
| framework-internal instrumentors (template rendering, ASGI internals) | you are debugging that layer specifically |

The test is not "is this data true" but "would anyone open this span during an incident."

### The `boto3sqs` exception: installed for adapters, not for spans

Manual SQS propagation needs `Boto3SQSGetter` / `Boto3SQSSetter`, which only
exist inside `opentelemetry-instrumentation-boto3sqs`. Installing a package for
its helper classes is legitimate; leaving its entry point active is not. The
three resolutions (code-based, zero-code, inline adapters) are in
`../tracing/queue_messaging.md`, "SQS carrier adapter". This is the one case
where "installed but deliberately inert" is the intended state, so write down
which of the three you chose.

### Trace these boundaries instead

```
HTTP request        queue publish       LLM call
external API call   queue consume       tool call
business phase      scheduled job run   agent invocation
database query — only when its query-level value earns the volume
```

---

## Ordering

The order and the failure each step prevents are owned by `sdk_bootstrap.md`, "Startup order". With several instrumentors it looks like this:

```python
configure_observability(telemetry_config(settings))

HTTPXClientInstrumentor().instrument()
RedisInstrumentor().instrument()
SQLAlchemyInstrumentor().instrument(engine=engine)

app = FastAPI(lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)
```

`SQLAlchemyInstrumentor` needs the engine, so create the engine here rather than at import time in another module.

Call each `instrument()` exactly once. Calling it twice — easy to do with a dev reloader or a test suite that re-imports the app — produces duplicate spans.

Record the activation owner explicitly:

| Setup | Installation owner | Activation owner |
| --- | --- | --- |
| Code-based | dependency lock/build | startup module's `.instrument()` calls |
| Zero-code | dependency lock plus `opentelemetry-bootstrap` during build | `opentelemetry-instrument` launcher |

Never let both activation owners run in one process (`sdk_bootstrap.md`, provider ownership).

AWS Lambda is a separate activation shape: the selected instrumentation layer
and `AWS_LAMBDA_EXEC_WRAPPER` own activation. Do not add the normal
`opentelemetry-instrument` launcher or a second manual invocation wrapper. Read
`../tracing/lambda_functions.md` before choosing the layer, propagator, and
Collector extension.

---

## Zero-code mode

`opentelemetry-instrument` configures the SDK and activates every installed instrumentor before your app is imported:

```bash
opentelemetry-bootstrap -a install     # resolve matching instrumentation packages
OTEL_SERVICE_NAME=chat-api \
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
opentelemetry-instrument uvicorn app:app
```

Use it when broad coverage matters more than control, or when application changes are expensive. Two constraints:

1. One owner: no in-code `configure_observability()` or `.instrument()` call (`sdk_bootstrap.md`).
2. Run `opentelemetry-bootstrap` when building the image, and lock the resulting packages. Letting each container start-up resolve its own instrumentation set makes deployments non-reproducible.

Business spans and custom metrics still have to be written by hand. Zero-code cannot infer `invoke_agent support_agent` or `app.pricing.updates`.

Disable one instrumentor without uninstalling it using its **entry-point name**, which is not always the package-name suffix — `opentelemetry-instrumentation-boto3sqs` registers as `boto3`:

```bash
OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=boto3,urllib3 \
opentelemetry-instrument python worker.py
```

---

## When automatic and manual instrumentation collide

Two owners of one boundary means two spans per operation — the failure mode SKILL.md rule 5 exists to prevent. It bites hardest on queue libraries, where an automatic consumer span plus a hand-written one doubles every message. `../tracing/queue_messaging.md`, "Automatic queue instrumentation may already own this", owns that decision — the shape and legacy schema the instrumentor produces, how to disable just that entry point, and what disabling it costs on the producer side. Read it before installing or removing a queue instrumentor.

Whatever you decide: do not "fix" a duplicate by leaving both and filtering in the Collector, and re-check the exported shape after any instrumentation upgrade — these semantics are version-specific.

---

## Verification

After installing packages and starting the service, send one request and confirm:

- an HTTP `SERVER` span exists with `http.route` set to a **template**, not a raw path with an ID in it;
- outbound calls produce `CLIENT` spans that are children of it;
- database spans appear only for queries you care about;
- there is exactly one span per logical operation, not two.

Span count per request is the fastest smoke test. If a simple health check produces forty spans, an instrumentor is too chatty — remove it.
