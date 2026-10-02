# Development and Staging Collector Configuration

Development and staging optimise for **debugging visibility**, not cost. That means:

```
no trace sampling
no unnecessary filtering
full metrics
```

If you cannot reproduce a production incident in staging because staging sampled the trace away, the environment failed at its job. Add sampling to a lower environment only when telemetry volume genuinely makes it impractical, and say so in the config comments.

---

## Development

Small limits, a debug exporter you can actually read, no credentials.

```yaml
# services/otel-collector/config.dev.yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 256
    spike_limit_mib: 64

  resource/environment:
    attributes:
      - key: deployment.environment.name
        value: development
        # insert, not upsert: never overwrite a value the service set itself.
        action: insert

  batch:
    timeout: 1s          # short, so spans appear while you are still looking
    send_batch_size: 128

exporters:
  # Prints telemetry to the Collector log. Invaluable locally, never in prod.
  debug:
    verbosity: detailed
    sampling_initial: 5
    sampling_thereafter: 200

  otlphttp/traces:
    endpoint: ${env:TRACES_ENDPOINT}

  otlphttp/metrics:
    endpoint: ${env:METRICS_ENDPOINT}

service:
  extensions: [health_check]
  telemetry:
    # This resource belongs to the Collector itself. The
    # resource/environment processor below labels telemetry passing through it.
    resource:
      attributes:
        - name: service.name
          value: otel-collector-gateway
        - name: deployment.environment.name
          value: development
    logs:
      level: info
      encoding: console
    metrics:
      level: normal
      readers:
        - periodic:
            # Bound the final shutdown export inside the 30 s Compose budget.
            timeout: 5000
            exporter:
              otlp:
                protocol: http/protobuf
                endpoint: ${env:SELF_METRICS_ENDPOINT}
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, resource/environment, batch]
      exporters: [debug, otlphttp/traces]

    metrics:
      receivers: [otlp]
      processors: [memory_limiter, resource/environment, batch]
      exporters: [debug, otlphttp/metrics]

    logs:
      receivers: [otlp]
      processors: [memory_limiter, resource/environment, batch]
      exporters: [debug]
```

Notes on the choices:

- **No sampling processor at all.** Every trace is kept.
- **`debug` with `verbosity: detailed`** prints full spans. The `sampling_*` settings stop a busy local run from flooding the terminal. It prints *everything on the span*, so with `CAPTURE_AI_CONTENT` enabled it writes prompts and completions into the Collector's own logs — do not point a log shipper at a Collector running this exporter, and do not enable it anywhere with real user content.
- **Application and self-metrics both leave by push.** The debug exporter gives
  local visibility; the configured OTLP destinations prove delivery.
- **Short batch timeout.** Five seconds feels broken when you are watching a terminal for a span you just triggered.
- **`memory_limiter` is still present.** It is cheap, and its absence in dev is how you discover in production that nobody ever tested with it.

### Compose

```yaml
# compose.yaml
services:
  otel-collector:
    build:
      context: ./services/otel-collector
      args:
        CONFIG_FILE: config.dev.yaml
    restart: unless-stopped
    ports:
      # Loopback only: nothing on the network can inject telemetry.
      - 127.0.0.1:4317:4317
      - 127.0.0.1:4318:4318
      - 127.0.0.1:13133:13133
    stop_grace_period: 30s
```

Services on the same Compose network export to `http://otel-collector:4318`, not the host mapping.

---

## Staging

Staging should be production's shape with production's *retention* behaviour removed. Same processors, same exporters, same redaction — no sampling.

`services/otel-collector/config.staging.yaml` is `config.prod.yaml` from
`production.md`, "Configuration" (open that file only for that block when
writing staging), with exactly these differences:

| Setting | `config.prod.yaml` | `config.staging.yaml` |
| --- | --- | --- |
| `extensions` | `health_check` plus `file_storage` (`directory: /var/lib/otelcol/storage`, persistent volume); `service.extensions: [health_check, file_storage]` | `health_check` only; `service.extensions: [health_check]` |
| `memory_limiter` | `limit_mib: 1024` (`# MEASURE:`), `spike_limit_mib: 256` | `limit_mib: 512`, `spike_limit_mib: 128` |
| `resource/environment` value and `service.telemetry.resource` `deployment.environment.name` | `production` | `staging` (still `action: insert`) |
| `tail_sampling` | defined and in the traces pipeline | absent: staging keeps everything |
| `batch` | `timeout: 5s`, `send_batch_size: 1024` | `timeout: 5s`, `send_batch_size: 512` |
| Trace exporter name and variables | `otlphttp/apm`, `${env:APM_ENDPOINT}`, `${env:APM_AUTHORIZATION}` | `otlphttp/traces`, `${env:TRACES_ENDPOINT}`, `${env:TRACES_AUTHORIZATION}` |
| Trace exporter queue and retry | `queue_size: 10000`, `storage: file_storage`; `max_elapsed_time: 10m` | `queue_size: 2000`, in memory (no `storage`); `max_elapsed_time: 5m` (same `initial_interval: 5s`, `max_interval: 30s`) |
| `otlphttp/metrics` and `otlphttp/logs` | `sending_queue` (`queue_size: 10000`, `storage: file_storage`) and `retry_on_failure` | `endpoint` and `Authorization` header only |

Everything else is identical: the OTLP receivers; `attributes/drop_secrets`,
`attributes/drop_span_exception_detail`, and `attributes/drop_payloads`, so
redaction bugs surface here, not in production; the self-telemetry service
name, JSON `info` logs collected from stderr by the platform log agent (never
fed back through this Collector's own OTLP receiver), and the periodic
self-metrics reader with `timeout: 5000`; and every pipeline's processor order.
The logs pipeline keeps `attributes/drop_secrets` but never
`attributes/drop_span_exception_detail`: secrets go, exception detail stays,
because the log record is the only carrier the error contract leaves for it
(`../conventions/errors.md`).

The one thing staging must share with production is **redaction**. A staging config without it means the first real test of the redaction rules happens in production with real user data.

Use separate backend credentials per environment, and keep environments visually separated on dashboards by `deployment.environment.name`.

### GenAI destination views are not sampling

"No unnecessary filtering" does not mean every trace backend must receive identical spans and
attributes. When a lower environment includes a GenAI backend, keep the same destination contract
as production (`genai_projection.md`) while removing only retention sampling: no `tail_sampling`
processor is present.

Use the marker and filter from `genai_projection.md`, and exercise them in development and staging so a
missing root or business ancestor is found before production. Do not replace this with a second
application provider or detached GenAI roots.

---

## Verify

Send one request through an instrumented service and confirm:

```bash
docker compose logs --tail=200 otel-collector | head -60
```

- the metrics backend contains application metrics such as `app.*`, `gen_ai.*`,
  or `http.server.*` from the canary;
- the monitoring destination contains this Collector's
  `otelcol_process_uptime`; receiver/export counters increase and
  `otelcol_exporter_send_failed_*` stays at zero;
- the debug exporter prints spans with your `service.name` and populated attributes;
- the backend can find `service.name=<your service>`;
- staging: canary secrets (a fake API key, email, and authorization header)
  reach no backend, and a canary exception's stack trace reaches the log
  backend but not the span;
- with a GenAI backend: `genai_projection.md`, "Acceptance invariants".

Container logs alone are not proof of delivery. Look in the backend.
