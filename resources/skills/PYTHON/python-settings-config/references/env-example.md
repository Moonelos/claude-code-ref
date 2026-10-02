# `.env.example`

The runtime contract of one deployable, safe to commit. It matches the
scaffolds in `settings-py.md`, `secrets-py.md` and `config-yaml.md`.

## Files

| File | Answers | Content |
| --- | --- | --- |
| `services/<name>/.env.example` (or the project root for a single service) | What does this process read at startup, whatever starts it? | The complete contract, in the three sections below |
| repository-root `.env.example` | What does the deployment tool need to start the stack? | Image pins, credential passthrough, coordinates Compose or Helm injects |

The root file never replaces a service file. Keys they share must agree. The root
file's contents and its explicit Compose mapping are owned by
`python-repository-setup` (fallback
`../../python-repository-setup/references/docker-compose.md`).

## Sections

Exactly three, in this order; omit an empty one.

- **REQUIRED:** `ENVIRONMENT_NAME` first, then every env-only field without a
  default, then the secrets with fake local values. Named
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

# --- Secrets. Fake local values; deployed, the platform injects the real ones.
DATABASE_DSN=postgresql+psycopg://app:replace-me@127.0.0.1:5432/app
LLM_API_KEY=replace-me
SERVICE_ACCOUNT={"username":"replace-me","password":"replace-me"}

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

One assertion under `contract/` catches the drift that breaks startup: the
REQUIRED names equal the env-only `Settings` fields plus the `Secrets` fields
(`SecretSources` fields when the service fetches secrets itself), plus any documented SDK passthrough. OVERRIDABLE and OPTIONAL are
guidance for readers and are not asserted.

```python
from my_service.config.secrets import Secrets
from my_service.config.settings import ENV_ONLY_FIELDS

ENV_EXAMPLE = Path(__file__).parents[3] / ".env.example"  # tests/contract/config/
SDK_PASSTHROUGH: frozenset[str] = frozenset()  # e.g. {"AWS_PROFILE"}
SECTIONS = frozenset({"REQUIRED", "OVERRIDABLE", "OPTIONAL"})


def required_names(path: Path) -> set[str]:
    """Uncommented assignments between the REQUIRED header and the next section."""
    names: set[str] = set()
    in_required = False
    for line in path.read_text(encoding="utf-8").splitlines():
        words = line.split()
        if len(words) > 1 and words[0] == "#" and words[1] in SECTIONS:
            in_required = words[1] == "REQUIRED"
        elif in_required and "=" in line and not line.startswith("#"):
            names.add(line.split("=", 1)[0])
    return names


def test_required_section_matches_settings() -> None:
    expected = {name.upper() for name in ENV_ONLY_FIELDS | set(Secrets.model_fields)}
    assert required_names(ENV_EXAMPLE) == expected | SDK_PASSTHROUGH
```
