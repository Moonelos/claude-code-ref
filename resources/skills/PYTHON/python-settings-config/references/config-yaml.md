# `config/*.yaml`

YAML baselines for the scaffold in `settings-py.md`. Location, layering and
ownership rules are in `../SKILL.md`.

YAML ships inside the built artifact and is shared by every deployment of an
environment. It therefore holds only application policy that is correct for
all of them: never secrets, topology, infrastructure outputs, GenAI runtime
coordinates, or `ENVIRONMENT_NAME`. Keys are the snake_case field names; a
nested section is a nested map.

## Layout

```text
config/
├── base.yaml                 # required: every policy key
├── local.yaml                # required per environment: only keys that differ
├── staging.yaml
├── production.yaml
└── services/                 # multi-service repositories; optional layers
    ├── <service>.yaml
    └── <service>.<environment>.yaml
```

Keep existing environment names (`dev`, `prod`) and an existing layout.

## Examples

`config/base.yaml`

```yaml
# Application policy for every environment. No secrets, no topology.
log_level: INFO
secret_provider: remote
log_full_exception_trace: false   # safe projection; see otel exception detail
request_timeout_seconds: 30
batch_size: 50
retry:
  max_attempts: 5
  initial_backoff_seconds: 0.5
  max_backoff_seconds: 30
  jitter: 0.2
```

`config/local.yaml`

```yaml
log_level: DEBUG
secret_provider: env
log_full_exception_trace: true
```

`config/staging.yaml`

```yaml
# Same policy as base.yaml.
```

`config/production.yaml`

```yaml
log_level: WARNING
retry:
  max_attempts: 8
```
