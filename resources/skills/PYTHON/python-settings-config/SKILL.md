---
name: python-settings-config
description: >
  Create, extend, or review typed configuration for a Python service. Use for
  Pydantic settings, YAML application baselines, environment contracts,
  `.env.example`, secret models, and local or remote secret-provider integration.
---

# Settings & Secrets

Give every value one owner, one typed declaration and one `.env.example` line.
Invalid configuration fails at process start, before accepting traffic or
consuming messages; secrets never reach logs or errors.

## Pattern

- **Existing service:** preserve its value sources, YAML layout, env names and
  flat/nested shape. Propose a migration (env-only to YAML, a new layout,
  renamed variables, a different grouping) separately; perform it only when asked.
- **New service:** YAML application baselines plus an env deployment contract.
  Use env vars plus Python defaults only when the user opts out of YAML.
- **Grouping:** new services start flat. Nest a cohesive unit (fields consumed
  and validated together, such as a retry policy) as a frozen section model.
  Nesting renames its variables (`RETRY__MAX_ATTEMPTS`), so it is a contract change.
- **Env binding:** `case_sensitive=False`, no `alias=` unless the env name
  really differs. Only a platform needing case-sensitive names uses
  `alias_generator=str.upper`. Existing aliases change only as a migration.

## Ownership

Classify a value before adding it. Each row has exactly one authoritative home.

| Value kind | Owner | Python declaration | `.env.example` | Test |
| --- | --- | --- | --- | --- |
| No legitimate operator choice, incl. a one-value `Literal` | code | constant beside its consumer (a temporary pin names its removal condition) | — | — |
| `ENVIRONMENT_NAME` | env-only | `environment_name: EnvironmentName`, no default | REQUIRED, first | missing fails naming it |
| Topology: regions, hosts, ports, base URLs, infra-created resource names, secret-backend coordinates (vault URL, project) | env-only | bare typed annotation, no default | REQUIRED | missing fails; key absent from YAML |
| GenAI runtime: model IDs, provider deployments, endpoints, API versions | env-only | bare typed annotation, no default | REQUIRED | same |
| Listener bind host/port | launcher command | none; if the process binds itself, env-only, no default | REQUIRED if read | — |
| Application policy: retries, limits, timeouts, thresholds, feature flags, prompt versions, supported-provider enum, owned key prefixes and relative API paths | YAML | constrained annotation, **no default** | OVERRIDABLE, useful ones only | YAML keys = model fields; validators |
| Secret provider mode | YAML per environment | `secret_provider: Literal["env", "remote"]` | — | local resolves without the remote |
| Credentials, incl. any DSN with a password | secret | `RequiredSecret` on `Secrets` | REQUIRED › secrets | sentinel never leaks |
| Secret source variable (payload locally, locator deployed) | secret boundary | field on the secret-source model, never `Settings` | REQUIRED › secrets; deployed form commented | provider selection |
| Platform identity: instance ID, release version | platform | `str \| None = None` or `"unknown"` | OPTIONAL | — |
| Exception detail | YAML per environment; `base.yaml` holds the safe value | `log_full_exception_trace: bool`, no default | — | `base.yaml` is safe |
| Diagnostics: content capture, export interval | code default, safe everywhere | `bool = False` etc. | OPTIONAL | default is the safe value |
| Telemetry collector endpoint | env-only | `AnyHttpUrl \| None = None` (unset disables export) | OPTIONAL | — |
| Config-dir escape hatch | env-only, read before `Settings` | not a field | OPTIONAL | — |

Classification tests:

- A value that could differ between two deployments of one environment, or that
  infrastructure creates, names or wires, is env-only, even if identical today.
- A bucket is topology; the key prefix the application owns inside it is policy.
  A base URL is topology; the relative route joined to it is policy or code.
- Never copy an env-only value into YAML as documentation. A YAML key that every
  deployment overrides does not belong in YAML.
- Only OPTIONAL rows carry Python defaults; anything that changes business
  behaviour is YAML policy without one.
- Exception detail is YAML policy with no Python default: `base.yaml` sets the
  safe value and an environment file overrides it; never derived from
  `ENVIRONMENT_NAME` in code. See `python-logging`
  (`../python-logging/references/errors-and-security.md`, Exception detail).

## Declaring fields

- A bare annotation declares a field: `x: int` is required, `x: int = 5` has a
  default. Never write `Field(...)` or `Field(default=...)` with nothing else.
- Use `Field` only for behaviour or information: a constraint, a differing alias,
  `default_factory`, `exclude`/`repr=False`, or a `description` saying what the
  name, type and default don't (what `None` does, why a bound exists). Units go
  in names (`timeout_seconds`); the env contract is documented in `.env.example`.
- Use the narrowest type and the aliases in `references/settings-py.md`: durations
  and ratios reject `inf`/`nan`; "disabled" is `X | None`; upper bounds only for
  real limits. See `python-code-conventions`
  (`../python-code-conventions/SKILL.md`, Named types and constraints).
- Single-field rules live in the type. A `@model_validator(mode="after")` checks
  only relationships or environment-dependent requirements: one per concern,
  naming both fields, never mutating `self`.
- URL types append `/`: compare issuers, audiences and callbacks as `str` with a
  `pattern`, and join base URLs and paths in one helper.
- **No shadow defaults:** a YAML- or env-owned value never reappears as a literal
  or default on a dataclass, constructor, prompt builder or port. Grep and delete.

## Sources and layout

- Precedence: constructor kwargs, process env, `.env`, merged YAML, class defaults.
- `src/<package>/config/` holds Python modules (`settings.py`, `secrets.py`),
  never YAML. YAML lives in `config/` at the project root; in a multi-service
  repository, one shared `config/` at the repository root. A per-service
  `pyproject.toml` or `.env.example` does not imply per-service YAML; create it
  only on explicit request.
- Layers merge from `base.yaml`, `{environment}.yaml`, `services/<svc>.yaml`,
  `services/<svc>.{environment}.yaml`. The first two are required and a missing
  file raises; service layers are optional, so don't create empty ones. An
  environment file holds only keys that differ from `base.yaml`.
- Discover `config/` by walking up from the settings module's file, never from
  the working directory or a fixed `parents[N]`.
- Extract the YAML loader to a library only when two or more services copy it
  verbatim and the copies drifted, or a shared config library already exists.
  The service always owns its `Settings` schema.

## Flow into the application

- Only `config/`, `bootstrap/` and `main.py` import `Settings` or `Secrets`.
  Bootstrap calls `load_settings()` and `load_secrets()` once, then builds clients.
- Bootstrap maps settings into small frozen policy objects owned by the action or
  adapter (one named mapping function each, plain values, required keyword-only
  fields). Never pass the whole `Settings` downstream or store `Secrets` on
  `app.state`. A shared library's own config object and test factories are exempt.
- Probes, admin CLIs and diagnostics reuse the service's loaders and add only
  their own fields; a separate one-shot job with three or fewer inputs may parse
  an injected `Mapping[str, str]`, still masking secrets.
- Read `os.environ` only in `config/`. Pass resolved values to SDKs explicitly;
  bridge into `os.environ` only in one bootstrap helper when an SDK has no API for it.

## References and tests

- `references/settings-py.md`: `Settings` scaffold, types, validators, `load_settings()`, variants, tests.
- `references/secrets-py.md`: secret rules, sources, remote loading (only when the
  user names a backend), sentinel test.
- `references/config-yaml.md`: YAML layout and baseline examples.
- `references/env-example.md`: every deployable's file has exactly three sections,
  REQUIRED, OVERRIDABLE, OPTIONAL; template and contract test.

Test validators, cross-field invariants, redaction and the document-to-model
contract, not literal defaults or pydantic-settings itself. For placement, see
`../python-service-architecture/references/testing.md` (Profiles and markers);
for test design, see `pytest` (`../pytest/SKILL.md`).
