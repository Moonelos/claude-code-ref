# The OpenTelemetry Collector Component

The Collector is a deployable component of the system, not a config file appended to a service. Treat it like a service: its own directory, its own image pin, its own configs per environment, its own monitoring.

---

## Why it exists

Without a Collector, every service holds backend endpoints and credentials, and changing a destination means redeploying every service.

```
application
    │ OTLP
    ▼
OpenTelemetry Collector
    ├── traces  → trace backend (and/or a GenAI backend)
    ├── metrics → metrics backend
    └── logs    → log backend
```

With it, applications export plain OTLP to one internal endpoint and know nothing about vendors. Credentials, redaction, sampling, retries, and fan-out all live in one place, changed without touching application code.

Keep vendor-specific configuration at the Collector boundary. Vendor attribute names and API keys should not appear in business code.

---

## Layout

In a monorepo it lives beside the services, following the repo's own convention:

```
services/
    api/
    worker/
    otel-collector/
        Dockerfile
        config.dev.yaml
        config.staging.yaml
        config.prod.yaml
        README.md
```

`apps/` instead of `services/` if that is what the repo uses. Match the existing convention rather than introducing a new top-level directory.

Three separate configs, not one with conditionals. Development and production want genuinely different behaviour — full retention versus sampling, debug exporters versus real backends — and a single templated file makes both harder to read and to review.

---

## Choosing a distribution

Configuration cannot enable a component the binary does not contain. Pick the distribution by the components your config actually references.

| Distribution | Image | Choose when |
| --- | --- | --- |
| Core | `otel/opentelemetry-collector` | A narrow OTLP-in, OTLP-out pipeline |
| Contrib | `otel/opentelemetry-collector-contrib` | You need `tail_sampling`, `transform`, `file_storage`, `prometheus_remote_write`, or a vendor exporter |
| Kubernetes | `ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-k8s` | Kubernetes, and its component set covers your config |
| Custom (OCB) | your registry | You need a minimized, reviewed component set |

Most production configs in this skill need **Contrib**, because `tail_sampling` and `transform` are Contrib components.

Verify before deploying:

```bash
docker run --rm otel/opentelemetry-collector-contrib:0.159.0 components
```

Compare the output against every component ID in your config. Look up the current release before pinning — the Collector moves fast, and `0.159.0` was released in mid-August 2026.

## Pin three things independently

1. the image version, and after promotion the image digest;
2. the Helm chart or Operator version;
3. the config revision.

Never run `latest`. A chart upgrade can change Services, probes, and security defaults without any change to your values file.

```dockerfile
# services/otel-collector/Dockerfile
FROM otel/opentelemetry-collector-contrib:0.159.0

# Config is baked in per environment via build arg, or mounted at runtime.
ARG CONFIG_FILE=config.dev.yaml
COPY ${CONFIG_FILE} /etc/otelcol/config.yaml

CMD ["--config=/etc/otelcol/config.yaml"]
```

Mounting the config at runtime (a ConfigMap or a volume) is equally valid and usually better in Kubernetes, because a config change does not require a rebuild. Baking it in gives you an immutable artifact. Pick one and say which.

---

## Topology

| Topology | Use when | Cost |
| --- | --- | --- |
| Gateway Deployment | Central routing, credentials, redaction, fan-out for many services | Shared dependency: needs ≥2 replicas and load balancing |
| Sidecar | One Collector failure must be isolated to one pod, or `localhost` is required | Highest overhead; one per replica |
| DaemonSet agent | Node-local logs/host metrics, or a node-local endpoint for workloads | One failure affects its node |
| Agent → gateway | Node-local collection plus central policy | Two tiers to configure, monitor, upgrade |

**Default, once discovery has chosen a Collector (`../discovery.md` §7): a gateway Deployment.** Use a DaemonSet only for work that is genuinely node-local, not because agents feel more production-like.

Tail sampling is the one exception to "any replica can handle any request": all spans of a trace must reach the same instance. That needs trace-ID-aware routing in front of the sampling tier — see `production.md`.

---

## Backend routing

The routing decision is: **which backend is allowed to receive which attributes?**

```
APM / general trace backend   trace shape, durations, error types, models,
                              token counts — no prompts or outputs
Metrics backend               aggregates only; no IDs or content
Log backend                   application logs, correlated, masked
GenAI backend (e.g. Langfuse) rooted GenAI view, prompts, outputs, sessions, scores
                              — when policy allows
```

Fanning one pipeline out to two exporters is simple but coarse: both destinations get identical data. When they need different data, use separate pipelines.

```yaml
service:
  pipelines:
    traces/apm:
      receivers: [otlp]
      processors: [memory_limiter, redact_payloads, batch]
      exporters: [otlphttp/apm]

    traces/genai:
      receivers: [otlp]
      # filter/genai_projection keeps only the rooted GenAI view (genai_projection.md);
      # a destination-specific mapping processor, if any, follows it.
      processors: [memory_limiter, filter/genai_projection, batch]
      exporters: [otlphttp/genai]
```

### If a GenAI backend is one of the destinations

- Name pipeline exporters `otlphttp/...` or `otlp_grpc/...` explicitly. A bare `otlp` exporter (as opposed to the `otlp` receiver, which is still the correct name) is a deprecated alias for `otlp_grpc` on 0.159.0 and logs a startup warning: `"otlp" alias is deprecated; use "otlp_grpc" instead`.
- Send either a complete trace or the rooted, ancestor-closed GenAI projection
  (`genai_projection.md`), never only model leaves.
- A GenAI backend is a trace backend. Operational metrics go to the metrics backend.
- Vendor attributes (`langfuse.*`, and the like) are added in that backend's pipeline by a
  destination-specific `attributes` or `transform` processor, never in application code. The
  same branch maps the neutral `app.gen_ai.observation.input` / `output` presentation copies to
  the vendor's keys and deletes the neutral sources; every other trace branch deletes both.

Destination specifics — ingestion protocol, authentication, required headers, and the concrete
mapping processors — live in one file per backend under `../backends/`. Langfuse:
`../backends/langfuse.md`.

---

## One trace, two destination views

One application trace feeds both a main backend and a GenAI backend; the destination contract,
the `app.telemetry.category="genai"` marker, the Collector filter, and the acceptance invariants
live in `genai_projection.md`. Load it whenever a specialized GenAI trace destination is
configured or reviewed.

---

## Validate before deploying

Run the exact production image against the exact config:

```bash
docker run --rm \
  --volume "${PWD}/config.prod.yaml:/etc/otelcol/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:0.159.0 \
  validate --config=/etc/otelcol/config.yaml
```

Do this in CI on every config change. A bad telemetry config creates blind spots exactly when you need visibility.

Then check both ends:

```bash
curl --fail http://127.0.0.1:13133/            # health
```

A health check proves the process is running. It does **not** prove the backend
is accepting data. Query the monitoring backend for this Collector's
`otelcol_process_uptime`, then confirm receiver/exporter counters change after
sending a canary through the application pipeline.

---

## Self-telemetry is part of the deployment

A Collector is another production service. Its workload is telemetry, so its
own failure mode is a blind spot unless a separate monitoring path observes it.
Do not call a deployment complete with only an OTLP receiver and backend
exporters.

The minimum baseline is:

| Signal | Baseline |
| --- | --- |
| Internal metrics | `service.telemetry.metrics.level: normal`, pushed directly to an independent monitoring destination with the embedded periodic OTLP reader |
| Internal logs | `INFO`; JSON in shared environments, emitted to `stderr` for the platform log agent or sent directly to an independent OTLP endpoint |
| Resource identity | A stable logical `service.name` per Collector role, `deployment.environment.name`, and the automatically generated `service.instance.id` |
| Internal traces | Off by default. They are experimental and useful only for time-bounded diagnosis when metrics and logs cannot explain a pipeline problem |

The examples in `dev_staging.md` and `production.md` make this baseline
explicit. The Collector supplies its own name, version, and random instance ID
by default, but explicitly naming the logical role keeps dashboards stable and
separates `otel-collector-agent`, `otel-collector-gateway`, and
`otel-collector-tail-sampler`. Do not hard-code `service.instance.id`; each
replica needs its own value.

`service.telemetry.resource` labels the Collector's **own** metrics, logs, and
traces. A `resource/environment` processor in `service.pipelines` labels the
application telemetry passing through the Collector and does not affect
self-telemetry. Configure both planes deliberately.

The health extension and self-telemetry answer different questions:

- `health_check` proves that the process is responsive enough to answer a
  probe;
- internal metrics and logs show whether receivers, processors, queues, and
  exporters are working;
- a canary found in the backend proves end-to-end delivery.

None of the three substitutes for another.

### Keep the monitoring path independent

Use the embedded periodic OTLP reader under `service.telemetry` to push
self-metrics directly to a separate monitoring endpoint. It bypasses the
application pipelines, so a broken application exporter cannot erase its own
evidence. Do not create a Prometheus reader or expose a metrics listener.

On the pinned 0.159.0 image, the direct self-metrics path has this exact shape:

```yaml
service:
  telemetry:
    metrics:
      level: normal
      readers:
        - periodic:
            # Reader-level budget for collection, export, and the final
            # shutdown flush. This example assumes a 30 s termination budget.
            timeout: 5000
            exporter:
              otlp:
                protocol: http/protobuf
                endpoint: ${env:SELF_METRICS_ENDPOINT}
                headers:
                  Authorization: ${env:SELF_METRICS_AUTHORIZATION}
```

The exporter key is `otlp`, not `otlp_http`, and this pin expects `headers` as
a plain map. Validate that schema again on every image upgrade: the declarative
SDK configuration is still development-status. The destination must not be
this Collector's own OTLP receiver or another path that depends on the pipeline
being observed.

A periodic reader performs one final collection and export when its meter
provider shuts down. Never leave that reader's `timeout` implicit: a monitoring
endpoint that accepts a connection and then hangs can otherwise consume the
Collector's whole termination grace period, preventing application exporters
and their sending queues from finishing cleanly. Choose a measured reader
timeout comfortably below the platform grace period and leave explicit budget
for application-pipeline shutdown. The `5000` above is a reviewed example for
the 30-second Compose/ECS budget, not a universal production value.

Test the bound with a sink that accepts the TCP connection but never responds;
an invalid hostname exercises fast DNS failure and does not prove the timeout.
Confirm the Collector stops before the platform deadline and that queued
application telemetry still drains. Record the exit code separately: a failed
final self-metrics export can still produce a non-zero process exit even when
the timeout bound works; do not hide it with a PID-1 wrapper or
alarm on a bare non-zero exit without also distinguishing expected stops.

Do not send a Collector's internal logs, metrics, or experimental traces to its
own OTLP receiver and then through the same pipeline being observed. That
couples the observer to the failure, can create feedback or recursion, and
makes an exporter outage erase the evidence of the outage. When a two-tier
deployment must observe itself, have the agent and gateway report to a separate
monitoring tier or backend, with an explicit loop analysis.

Use TLS and authentication for direct OTLP export across a trust boundary, with
credentials from the same secret-management path as other exporters. If the
embedded reader cannot satisfy the destination's authentication mechanism —
for example, an extension-owned signer — push to a distinct monitoring
Collector or agent that can authenticate onward. Never route self-metrics into
this Collector's own receiver merely to gain access to its application
pipeline exporters.

`normal` is the production starting level. `detailed` adds cost and dimensions;
enable it for a stated diagnostic need, verify cardinality, and roll it back.
Keep production internal logs at `INFO` unless a time-bounded incident requires
`DEBUG`. Internal metric names, attributes, log formats, and especially trace
spans have different stability levels, so verify dashboards and alerts against
the pinned image during every upgrade; `../compatibility.md` owns that check.

The authoritative schema and metric inventory are in the
[Collector internal telemetry documentation](https://opentelemetry.io/docs/collector/internal-telemetry/).

### Monitor and alert on rates, not historical counter values

Collector counters are cumulative. Alert on a sustained positive `rate()` or
`increase()` over an operationally justified window, not on `counter > 0`; one
old failure would otherwise alert forever. OTLP preserves the instrument names,
but a backend can still translate them on ingest. Inspect the actual backend
series after an image or backend upgrade before promoting alert rules.

| Condition | What to use | Meaning |
| --- | --- | --- |
| Collector unavailable | backend absence-over-window query, for example `absent_over_time(otelcol_process_uptime{...}[5m])`, plus platform restarts | The observer itself is unavailable; this is the first page |
| Receiver backpressure | increasing `otelcol_receiver_refused_{spans,metric_points,log_records}` | Senders were refused; data loss depends on their retry behaviour |
| Definite queue loss | increasing `otelcol_exporter_enqueue_failed_{spans,metric_points,log_records}` | Telemetry could not enter an exporter queue and was dropped |
| Delivery impairment | sustained increase in `otelcol_exporter_send_failed_*` | The destination is failing; retries mean this alone is not proof of permanent loss |
| Queue saturation | `otelcol_exporter_queue_size / otelcol_exporter_queue_capacity` high and rising | The downstream outage or throughput deficit is consuming the buffer; choose a threshold and window from measured bursts |
| Memory pressure | RSS approaching the container limit, OOM/restarts, or increasing `otelcol_processor_memory_limiter_refused_*` | The Collector is shedding load; alert before the hard container limit, not at a copied percentage |
| Pipeline stall | accepted input rises while processor output or exporter sent counts stop, adjusted for intentional filtering and sampling | Data entered but is no longer progressing |
| Tail-sampling failure | increasing `otelcol_processor_tail_sampling_sampling_trace_dropped_too_early` or `otelcol_processor_tail_sampling_sampling_policy_evaluation_error`, late-span age/ratio, or excessive decision latency | The sampling tier is undersized, late, or evaluating policies incorrectly |

Dashboard accepted/refused input, processor ingress/egress, sent/failed output,
queue size/capacity, CPU, RSS, uptime/restarts, and component-specific processor
metrics per signal, component, and Collector instance. Compare these with
producer-side counts and backend ingest. Do not demand equality across a
pipeline that intentionally filters, aggregates, or tail-samples; reconcile
each deliberate reduction instead.

Silent telemetry loss during an incident is worse than no telemetry, because
you will trust the empty dashboard.

---

## Security

- Bind receivers to private networks; never expose OTLP, pprof, or zPages publicly.
- TLS or mTLS across trust boundaries — **including application → Collector**, not only Collector → backend. Telemetry carries route templates, error types, tenant tiers, and (when capture is on) prompts. Configure the receiver's `tls` block and point the application at `https://`; the SDK reads CA and client material from `OTEL_EXPORTER_OTLP_CERTIFICATE`, `OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE`, and `OTEL_EXPORTER_OTLP_CLIENT_KEY`. If the Collector requires a shared token instead, it goes in `OTEL_EXPORTER_OTLP_HEADERS` and is a credential like any other.
- Backend credentials from a secret store, injected only into the Collector — never into application containers.
- Redact before data crosses a trust boundary.
- Treat OTLP headers containing Basic Auth as credentials: not in ConfigMaps, not in committed `.env` files, not in CI logs.

---

## Then

- `dev_staging.md` for the development and staging configs, including their
  self-telemetry identity and delivery path;
- `production.md` for sampling, redaction, and resilience in production.
