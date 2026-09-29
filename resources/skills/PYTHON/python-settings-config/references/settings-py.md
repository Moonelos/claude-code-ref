# `settings.py`

Scaffold for `src/<package>/config/settings.py`. The ownership rules are in
`../SKILL.md`; this file shows how they look in code. When adapting it, keep the
repository's environment names, grouping and existing env variable names.

## Scaffold (YAML baselines + env contract)

```python
"""Typed, non-secret service settings. Secrets live in config/secrets.py."""

import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationError,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

SERVICE_NAME = "my-service"
CONFIG_DIR_VARIABLE = "MY_SERVICE_CONFIG_DIR"

EnvironmentName = Literal["local", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
PositiveSeconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Ratio = Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)]
NonEmptyStr = Annotated[str, Field(min_length=1)]


def _reject_password(url: AnyUrl) -> AnyUrl:
    if url.password is not None:
        raise ValueError("URL embeds a password; move the credential to a secret")
    return url


CredentialFreeUrl = Annotated[AnyUrl, AfterValidator(_reject_password)]


class ConfigurationError(Exception):
    """Configuration is missing or invalid. Messages name fields, never values."""


class SettingsSection(BaseModel):
    """Base for every nested section: YAML typos inside a section fail startup."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RetrySettings(SettingsSection):
    max_attempts: PositiveInt
    initial_backoff_seconds: PositiveSeconds
    max_backoff_seconds: PositiveSeconds
    jitter: Ratio

    @model_validator(mode="after")
    def _check_backoff_order(self) -> Self:
        if self.initial_backoff_seconds > self.max_backoff_seconds:
            raise ValueError(
                "retry.initial_backoff_seconds must not exceed retry.max_backoff_seconds"
            )
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
        env_ignore_empty=True,  # Compose passes unset variables as ""
        extra="ignore",  # .env is shared with unrelated variables
        frozen=True,
        hide_input_in_errors=True,  # cache_url input may carry a password
    )

    # Env-only deployment contract: REQUIRED, never in YAML, no default.
    environment_name: EnvironmentName
    downstream_base_url: AnyHttpUrl
    cache_url: CredentialFreeUrl
    primary_model_id: NonEmptyStr

    # YAML application policy: no Python default.
    log_level: LogLevel
    request_timeout_seconds: PositiveSeconds
    batch_size: PositiveInt
    log_full_exception_trace: bool
    retry: RetrySettings

    # OPTIONAL: platform identity and diagnostics whose default is safe everywhere.
    service_instance_id: str | None = None
    otlp_endpoint: AnyHttpUrl | None = Field(
        default=None, description="Telemetry export is disabled when unset."
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        environment = _environment_name(init_settings, env_settings, dotenv_settings)
        yaml_source = PolicyYamlSource(
            settings_cls, yaml_file=yaml_layers(environment), deep_merge=True
        )
        return (init_settings, env_settings, dotenv_settings, yaml_source, file_secret_settings)


ENV_ONLY_FIELDS = frozenset(
    {"environment_name", "downstream_base_url", "cache_url", "primary_model_id"}
)


class PolicyYamlSource(YamlConfigSettingsSource):
    """Merged YAML layers; a key that is not a policy field fails startup.

    The root model ignores unknown input because `.env` is shared, so without
    this check a mistyped key would be dropped silently and the tweak ignored.
    """

    def __call__(self) -> dict[str, Any]:
        document = super().__call__()
        policy_fields = {
            name for name, field in self.settings_cls.model_fields.items() if field.is_required()
        } - ENV_ONLY_FIELDS
        unknown = sorted(set(document) - policy_fields)
        if unknown:
            raise ConfigurationError(f"YAML keys are not policy fields: {', '.join(unknown)}")
        return document


def _environment_name(*sources: PydanticBaseSettingsSource) -> str:
    """Read the selector before YAML is chosen, in the same precedence as fields:
    init kwargs (tests, `Settings(environment_name="local")`), then env, then .env."""
    for source in sources:
        value = source().get("environment_name")
        if isinstance(value, str) and value:
            return value
    raise ConfigurationError("ENVIRONMENT_NAME is required")


def _config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_VARIABLE)
    if override:
        return Path(override)
    # Walk up from the installed module: works for source trees and site-packages.
    for parent in Path(__file__).resolve().parents:
        if (parent / "config" / "base.yaml").is_file():
            return parent / "config"
    raise ConfigurationError(f"No config/base.yaml above the package; set {CONFIG_DIR_VARIABLE}")


def yaml_layers(environment: str) -> list[Path]:
    config_dir = _config_dir()
    required = [config_dir / "base.yaml", config_dir / f"{environment}.yaml"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ConfigurationError(f"Missing config file(s): {', '.join(missing)}")
    service_layers = [
        config_dir / "services" / f"{SERVICE_NAME}.yaml",
        config_dir / "services" / f"{SERVICE_NAME}.{environment}.yaml",
    ]
    return [*required, *(path for path in service_layers if path.is_file())]


def describe_validation_error(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'model'}: {error['msg']}"
        for error in exc.errors(include_input=False, include_url=False)
    )


def load_settings() -> Settings:
    """Build Settings once, in the composition root."""
    try:
        return Settings()
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid settings: {describe_validation_error(exc)}") from None
```

Types: pick the narrowest Pydantic type before `str`/`int`/`float`: `Path`,
`UUID`, `Decimal` for money, `AwareDatetime`, `EmailStr`, `ByteSize` for sizes,
`AnyHttpUrl` for credential-free HTTP URLs. Put value-shape checks in the type
(`AfterValidator`), not in a one-field validator. Choose bounds from library
semantics (`max_overflow=0` is valid), and give one concept the same alias in
every service.

Notes on the scaffold:

- `Settings()` type-checks under the `pydantic.mypy` plugin, which
  `python-repository-setup` enables. Without the plugin, the accepted form is
  `Settings()  # type: ignore[call-arg]`, once, in `load_settings()`. Don't wrap
  it in a cached `get_settings()`; bootstrap calls `load_settings()` once.

- `from None` matters: `errors(include_input=False)` only cleans your message; a
  chained `ValidationError` would still print `input_value=...`.
- `_environment_name` raises explicitly; don't hide the raise inside an `or` chain.
  It reads `init_settings` first, so a test may pass `environment_name=` as a
  keyword instead of setting `ENVIRONMENT_NAME`.
- The root keeps `extra="ignore"` for `.env`; `PolicyYamlSource` restores
  strictness for YAML. Top-level YAML keys must be required, non-env-only
  fields; nested typos fail through `SettingsSection`'s `extra="forbid"`. Add
  every new env-only field to `ENV_ONLY_FIELDS` so YAML cannot set it.
- Keep each model validator small (about ten checks). Validate a policy object once. If bootstrap builds a frozen policy dataclass
  that checks itself in `__post_init__`, don't repeat the check on `Settings`.
- When variables were renamed, reject the old names with a migration message
  until no deployment sets them:

```python
_RENAMED_VARIABLES = {"HTTP_TIMEOUT": "REQUEST_TIMEOUT_SECONDS"}


def reject_renamed_variables() -> None:
    stale = sorted(name for name in _RENAMED_VARIABLES if name in os.environ)
    if stale:
        renames = ", ".join(f"{old} -> {_RENAMED_VARIABLES[old]}" for old in stale)
        raise ConfigurationError(f"Renamed variables are still set: {renames}")
```

## Variants

- **Env-only (explicit YAML opt-out):** return
  `(init_settings, env_settings, dotenv_settings)` and drop the YAML helpers,
  `PolicyYamlSource`, and `ENV_ONLY_FIELDS`.
  Policy fields then carry their safe Python defaults, the only case where they do.
- **Process env only** (the launcher already loads `.env`): set `env_file=None`,
  then `del dotenv_settings, file_secret_settings` and return
  `(init_settings, env_settings, yaml_source)`. `Secrets` must match.
- **Credentials on `Settings`:** a single-process job with one or two secrets may
  keep `RequiredSecret` fields here. Otherwise use `secrets.py`.

## Tests

Unit tests are hermetic; contract tests read the committed files.

```python
@pytest.fixture(autouse=True)
def runtime_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for key in list(os.environ):
        if key.split("__")[0].lower() in Settings.model_fields:
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)  # no stray .env
    monkeypatch.setenv(CONFIG_DIR_VARIABLE, str(tmp_path))
    return tmp_path


def test_backoff_order_is_enforced() -> None:
    with pytest.raises(ValidationError, match="initial_backoff_seconds"):
        RetrySettings(
            max_attempts=3, initial_backoff_seconds=5, max_backoff_seconds=1, jitter=0
        )


def test_environment_name_can_be_passed_directly(runtime_env: Path) -> None:
    (runtime_env / "base.yaml").write_text("", encoding="utf-8")
    (runtime_env / "local.yaml").write_text("", encoding="utf-8")
    with pytest.raises(ValidationError) as caught:  # policy fields are still missing
        Settings(environment_name="local")
    assert "environment_name" not in str(caught.value)


def test_mistyped_yaml_key_fails(runtime_env: Path) -> None:
    (runtime_env / "base.yaml").write_text("batch_szie: 10\n", encoding="utf-8")
    (runtime_env / "local.yaml").write_text("", encoding="utf-8")
    source = PolicyYamlSource(Settings, yaml_file=yaml_layers("local"))
    with pytest.raises(ConfigurationError, match="batch_szie"):
        source()


# contract/: every committed environment's layers pass the startup check in CI,
# not only the environment a developer happens to run.
@pytest.mark.parametrize("environment", ["local", "staging", "production"])
def test_committed_yaml_is_policy_only(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CONFIG_DIR_VARIABLE)
    PolicyYamlSource(Settings, yaml_file=yaml_layers(environment), deep_merge=True)()
```

Test each meaningful invalid combination and its valid boundary; don't assert
literal defaults one by one. If a class default on a YAML-owned field is kept
deliberately, a contract test asserts it equals every committed baseline. A test
that needs `Settings.model_construct()` to skip fields signals a missing
policy slice.
