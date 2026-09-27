# `.env.example`

The runtime contract of one deployable, safe to commit. It matches the
scaffolds in `settings-py.md`, `secrets-py.md` and `config-yaml.md`.

## Files

| File | Answers | Content |
| --- | --- | --- |
| `services/<name>/.env.example` (or the project root for a single service) | What does this process read at startup, whatever starts it? | The complete contract, in the three sections below |
| repository-root `.env.example` | What does the deployment tool need to start the stack? | Image pins, credential passthrough, coordinates Compose or Helm injects |

The root file never replaces a service file. Keys they share must agree.

## Sections

Exactly three, in this order; omit an empty one.

- **REQUIRED:** `ENVIRONMENT_NAME` first, then every env-only field without a
  default, then secret source variables with fake local values. Named
  sub-sections inside REQUIRED are fine (secrets; command-scoped inputs of a
  one-shot job). SDK credential passthrough the process needs is listed here,
  marked as such.
- **OVERRIDABLE:** commented YAML policy keys that developers commonly override,
  not a dump of every key. Values are those resolved for `ENVIRONMENT_NAME=local`.
  Under an explicit YAML opt-out, the useful overrides of Python defaults.
- **OPTIONAL:** platform identity, diagnostic switches, the telemetry endpoint and
  the config-dir escape hatch. Exception detail is YAML policy, not an env
  variable (`../SKILL.md`, Ownership).

Comment a variable only when its name, type and value don't already say what it
is, its unit, or what omission does. Never include real credentials.

## Template

```dotenv
################################################################################
# REQUIRED — startup fails naming the variable when one is missing
################################################################################
ENVIRONMENT_NAME=local
DOWNSTREAM_BASE_URL=http://127.0.0.1:9000
CACHE_URL=redis://127.0.0.1:6379/0
PRIMARY_MODEL_ID=replace-me

# --- Secrets. Locally each holds the payload; deployed, the deployment system
# injects the secret manager's locator into the same variable.
DATABASE_SECRET=postgresql+psycopg://app:replace-me@127.0.0.1:5432/app
LLM_API_KEY_SECRET=replace-me
# JSON object: {"username": ..., "password": ...}
SERVICE_ACCOUNT_SECRET={"username":"replace-me","password":"replace-me"}

################################################################################
# OVERRIDABLE — YAML policy; values shown are resolved for ENVIRONMENT_NAME=local
################################################################################
# LOG_LEVEL=DEBUG
# REQUEST_TIMEOUT_SECONDS=30
# RETRY__MAX_ATTEMPTS=5

################################################################################
# OPTIONAL — rare runtime-only variables
################################################################################
# SERVICE_INSTANCE_ID=
# Telemetry export is disabled when unset.
# OTLP_ENDPOINT=http://127.0.0.1:4318
# Only when config/ is not discoverable above the installed package.
# MY_SERVICE_CONFIG_DIR=
```

## Contract test

Parse the file into sections, then assert under `contract/`:

- REQUIRED names equal the env-only required `Settings` fields plus the
  `SecretSources` fields (plus documented passthrough).
- Every OVERRIDABLE name is a YAML policy key, and its value equals the value in
  the merged `local` baseline.
- OPTIONAL names are `Settings` fields with defaults, plus the escape hatch.
- Shared keys in the repository-root file match the service file.
- No comment merely restates the variable name.

```python
SECTION = re.compile(r"^# (REQUIRED|OVERRIDABLE|OPTIONAL) ")
ASSIGNMENT = re.compile(r"^#? ?([A-Z][A-Z0-9_]*)=(.*)$")


def parse_env_example(path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if header := SECTION.match(line):
            current = sections.setdefault(header.group(1), {})
        elif current is not None and (assignment := ASSIGNMENT.match(line)):
            current[assignment.group(1)] = assignment.group(2)
    return sections
```
