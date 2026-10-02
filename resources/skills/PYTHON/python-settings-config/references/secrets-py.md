# `secrets.py`

Scaffold for `src/<package>/config/secrets.py`. Ownership rules are in `../SKILL.md`.

## Rules

- `Secrets` holds only credential-bearing values. The environment name,
  timeouts and backend coordinates (vault URL, project ID) belong on `Settings`.
- Every secret model sets `hide_input_in_errors=True`. A loader that converts
  `ValidationError` or `SettingsError` raises with `from None`, naming the
  variable, never the value.
- A required secret is `RequiredSecret`, so an empty variable fails. Any value
  containing a credential, including a DSN with a password, is `SecretStr`; never
  `AnyUrl` or `PostgresDsn`, whose repr shows the password. Parse it after
  `.get_secret_value()`, inside the adapter or bootstrap that uses it. A
  credential-free URL on `Settings` is `CredentialFreeUrl`, which rejects a password.
- Secrets held outside Pydantic stay `SecretStr` or use `field(repr=False)`.
  Unwrapping helpers take `SecretStr | None`, never `object`.
- Credentials that must arrive together are one structured secret, or a model
  validator requires both or neither. Deployed environments reject static keys
  meant for local emulators.
- Each process loads only the secrets it needs; give processes with different
  needs their own model. A migration process (Alembic's `env.py`, a migrate
  entrypoint) loads a `MigrationSecrets` model with only `database_dsn`, and no
  `Settings`, so migrating never requires the service's other env variables:

  ```python
  class MigrationSecrets(BaseSettings):
      model_config = SettingsConfigDict(...)  # same as Secrets

      database_dsn: RequiredSecret
  ```
- Let pydantic-settings read `.env`; never hand-parse it.
- The payload schema belongs to the logical secret, not to where it is stored. A
  scalar (API key, token, DSN) is a plain string; never wrap it in a one-field
  JSON object (`{"dsn": ...}`). A multi-field credential is a JSON object with the
  same schema locally and deployed. If a managed store only offers a document
  (`username`, `password`, `host`, ...), model that document and build the DSN in
  the database adapter.

## Scaffold: the platform injects secrets (default)

The deployment platform (ECS task definition `secrets:`, a Kubernetes Secret,
Compose, the CI runner) resolves each secret and sets it as an environment
variable; locally `.env` holds the same variables with fake values. The service
only reads and validates them.

```python
"""Credential-bearing configuration, resolved once before any client is built."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError

from my_service.config.settings import (
    ConfigurationError,
    NonEmptyStr,
    describe_validation_error,
)

RequiredSecret = Annotated[SecretStr, Field(min_length=1)]


class ServiceAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    username: NonEmptyStr
    password: RequiredSecret


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_dsn: RequiredSecret
    llm_api_key: RequiredSecret
    service_account: ServiceAccount  # JSON object in SERVICE_ACCOUNT


def load_secrets() -> Secrets:
    """Build Secrets once, in the composition root."""
    try:
        return Secrets()
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid secrets: {describe_validation_error(exc)}") from None
    except SettingsError as exc:  # malformed JSON; the message names the field only
        raise ConfigurationError(f"Invalid secrets: {exc}") from None
```

## Variant: the service fetches secrets itself

Platform injection is preferred: the process needs no secret-backend SDK or
read permission, startup does not depend on the backend, and local development
is the same code path. Use this variant only when the platform cannot inject the
value, for example:

- a runtime whose environment variables are visible to anyone who can read the
  function or task configuration (AWS Lambda);
- the user names a backend the platform has no integration for (AWS Secrets
  Manager, Vault, GCP Secret Manager).

This scaffold fetches once at startup. It does not support rotation without a
restart or short-lived dynamic credentials (Vault database leases); those need
a refreshing client owned by the adapter that uses the credential, designed
separately.

If only some secrets are fetched, keep the injected ones as plain `Secrets`
fields and route only the fetched ones through source variables.

- Add `secret_provider: Literal["env", "remote"]` to `Settings` as YAML policy:
  `base.yaml` sets `remote`, `local.yaml` sets `env`. Test that local resolves
  without constructing the backend client.
- One neutral source variable per fetched secret (`DATABASE_SECRET`, not `*_ARN`
  or `*_VALUE`). With `env` it carries the payload; with `remote`, deployment
  tooling injects the backend's locator (never derived from `ENVIRONMENT_NAME`)
  and the loader fetches the payload.
- `Secrets` becomes a plain `BaseModel` (with the same `hide_input_in_errors`);
  the source variables live on a separate `SecretSources` settings model, never
  on `Settings`. `.env.example` lists the source variables under REQUIRED ›
  secrets, with the deployed form commented.

```python
FetchSecret = Callable[[str], str]
"""Maps a backend locator to its payload; bootstrap builds it around the SDK client."""


class Secrets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    database_dsn: RequiredSecret
    service_account: Json[ServiceAccount]


class SecretSources(BaseSettings):
    """Payloads when resolved from env; backend locators when remote."""

    model_config = SettingsConfigDict(...)  # same as Secrets in the default scaffold

    database_secret: RequiredSecret
    service_account_secret: RequiredSecret


def _payload(source: SecretStr, fetch: FetchSecret | None) -> str:
    value = source.get_secret_value()
    return value if fetch is None else fetch(value)


def load_secrets(fetch: FetchSecret | None) -> Secrets:
    """Resolve every secret; `fetch=None` reads payloads directly from env."""
    try:
        sources = SecretSources()
        return Secrets.model_validate(
            {
                "database_dsn": _payload(sources.database_secret, fetch),
                "service_account": _payload(sources.service_account_secret, fetch),
            }
        )
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid secrets: {describe_validation_error(exc)}") from None
```

Bootstrap selects the backend from the validated `settings.secret_provider`:
`None` for `env`, or a `FetchSecret` closure over the SDK client for `remote`.
Local development never constructs that client. Add a `Protocol` only when a
second remote backend exists. For a sync SDK called from async startup, see
`../../python-service-architecture/references/async-and-lifecycle.md` (Blocking I/O).
Resolve settings, then every secret, and only then construct clients.

## Test with a sentinel

Missing, malformed and cross-field failures must not show the payload anywhere.

```python
SENTINEL = "sentinel-7f3a"


def test_malformed_secret_is_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_DSN", SENTINEL)
    monkeypatch.setenv("LLM_API_KEY", SENTINEL)
    monkeypatch.setenv("SERVICE_ACCOUNT", f'{{"username": "", "password": "{SENTINEL}"}}')

    with pytest.raises(ConfigurationError) as caught:
        load_secrets()

    error = caught.value
    rendered = [str(error), repr(error), str(error.__cause__), str(error.__context__)]
    assert "service_account.username" in str(error)
    assert all(SENTINEL not in text for text in rendered)
```

Also assert `SENTINEL` is absent from `repr(secrets)`, `secrets.model_dump_json()`
and captured startup logs, and add the same test with malformed JSON
(`SERVICE_ACCOUNT='{bad'`).
