---
name: python-settings-config
description: >
  Create, extend, or review typed configuration for a Python service. Use for
  Pydantic settings and `BaseSettings` classes, environment variables, YAML
  application baselines and other config files, environment contracts,
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

Classify a value before adding it by asking these questions in order; the first
yes decides its one authoritative home.

| Question | Owner | Python declaration | `.env.example` |
| --- | --- | --- | --- |
| 1. Is it a credential, or does it contain one (incl. a DSN with a password)? | secret | `RequiredSecret` on `Secrets` | REQUIRED › secrets |
| 2. Could it differ between two deployments of one environment, or does infrastructure create, name or wire it (regions, hosts, ports, base URLs, resource names, secret-backend coordinates)? Env-only even if identical today. | env-only | bare annotation, no default | REQUIRED |
| 3. Is it behaviour someone may tune (retries, limits, timeouts, thresholds, feature flags, prompt versions, owned key prefixes, relative API paths)? | YAML | constrained annotation, **no default** | OVERRIDABLE, useful ones only |
| 4. None of the above: no legitimate operator choice, incl. a one-value `Literal` | code | constant beside its consumer (a temporary pin names its removal condition) | — |

Fixed cases the questions don't settle:

- `ENVIRONMENT_NAME`: env-only `environment_name: EnvironmentName`, no default,
  first line of REQUIRED; it selects the environment YAML layer.
- GenAI runtime (model IDs, provider deployments, endpoints, API versions):
  env-only, bare annotation, no default, REQUIRED.
- `log_full_exception_trace`: YAML with no Python default, the safe value
  (`false`) in `base.yaml` and overrides per environment; never derived from
  `ENVIRONMENT_NAME` in code. What it controls is owned by `python-logging`
  (`../python-logging/references/errors-and-security.md#exception-detail`).
- Secrets are injected as env vars by the platform by default. Only a service
  that fetches secrets itself adds `secret_provider` (YAML) and secret source
  variables (`references/secrets-py.md`, "Variant: the service fetches secrets
  itself").
- The only fields with Python defaults, listed under OPTIONAL: platform identity
  (`service_instance_id: str | None = None`), diagnostics whose default is safe
  everywhere (`capture_content: bool = False`), and the telemetry endpoint
  (`AnyHttpUrl | None = None`; unset disables export).
- Listener bind host/port belong to the launcher command; if the process binds
  itself, they are env-only. Never a YAML key.
- The config-dir escape hatch is read before `Settings` and is not a field.

A bucket is topology; the key prefix the application owns inside it is policy.
A base URL is topology; the relative route joined to it is policy or code. Never
copy an env-only value into YAML as documentation, and a YAML key that every
deployment overrides is env-only.

## Declaring fields

- Bare annotations and when `Field(...)` is allowed follow `python-code-conventions`
  (`../python-code-conventions/SKILL.md#data-containers`). For settings, the env
  contract is documented in `.env.example`, not in `Field` descriptions.
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

- Precedence: constructor kwargs, process env, `.env`, merged YAML, file secrets
  (`secrets_dir`), class defaults (`settings_customise_sources` in
  `references/settings-py.md`).
- `src/<package>/config/` holds Python modules (`settings.py`, `secrets.py`),
  never YAML. YAML lives in `config/` at the project root; in a multi-service
  repository, one shared `config/` at the repository root. A per-service
  `pyproject.toml` or `.env.example` does not imply per-service YAML; create it
  only on explicit request.
- Layers merge from `base.yaml`, `{environment}.yaml`, `services/<svc>.yaml`,
  `services/<svc>.{environment}.yaml`. The first two are required and a missing
  file raises; service layers are optional, so don't create empty ones.
- Create `{environment}.yaml` for every environment, even with no overrides, so
  everyone sees where an override goes. It starts with a header comment saying
  its keys override `base.yaml` for that environment, and holds only keys that
  differ from `base.yaml`.
- A YAML key that is not a policy field fails startup (`PolicyYamlSource` in
  `references/settings-py.md`), so a mistyped tweak is never silently ignored.
- Discover `config/` by walking up from the settings module's file, never from
  the working directory or a fixed `parents[N]`.
- For shared YAML-loading mechanics, see
  `../python-service-architecture/references/shared-libraries.md#configuration-mechanics`
  and its extraction triggers.
  The service always owns its `Settings` schema.

## Flow into the application

- Who may import `Settings`, `Secrets` and settings-slice types is owned by
  `python-service-architecture`
  (`../python-service-architecture/references/boundaries.md#config`).
  Bootstrap calls `load_settings()` and `load_secrets()` once, then builds clients.
- Bootstrap maps settings into small frozen policy objects and never passes the
  whole `Settings` downstream; the rule is owned by
  `../python-service-architecture/references/boundaries.md#bootstrap`.
- Probes, admin CLIs and diagnostics reuse the service's loaders and add only
  their own fields; a separate one-shot job with three or fewer inputs may parse
  an injected `Mapping[str, str]`, still masking secrets.
- Read `os.environ` only in `config/`. Pass resolved values to SDKs explicitly;
  bridge into `os.environ` only in one bootstrap helper when an SDK has no API for it.

## References and tests

- `references/settings-py.md`: `Settings` scaffold, types, validators, `load_settings()`, variants, tests.
- `references/secrets-py.md`: secret rules, the platform-injected `Secrets`
  scaffold, the self-fetching variant (only when the service must call a secret
  backend), sentinel test.
- `references/config-yaml.md`: YAML layout and baseline examples.
- `references/env-example.md`: every deployable's file has exactly three sections,
  REQUIRED, OVERRIDABLE, OPTIONAL; template and contract test.

Test that a missing REQUIRED value fails naming it, validators and cross-field
invariants, that secrets never leak (sentinel test), that committed YAML passes
`PolicyYamlSource`, and, when the service fetches secrets itself, that local
resolves without the backend client. Do
not test literal defaults or pydantic-settings itself. For placement, see
`../python-service-architecture/references/testing.md` (Profiles and markers);
for test design, see `pytest` (`../pytest/SKILL.md`).
