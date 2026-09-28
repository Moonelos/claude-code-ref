# `secrets.py`

Scaffold for `src/<package>/config/secrets.py`. Ownership rules are in `../SKILL.md`.

## Rules

- `Secrets` holds only credential-bearing values. The environment name,
  timeouts and backend coordinates (vault URL, project ID) belong on `Settings`.
- Every secret model sets `hide_input_in_errors=True`. A loader that converts
  `ValidationError` raises with `from None`, naming the variable, never the value.
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
  needs their own model.
- Let pydantic-settings read `.env`; never hand-parse it.

## Stable source variables

One neutral variable per logical secret (`DATABASE_SECRET`, not `*_ARN` or
`*_VALUE`). With `secret_provider: env` it carries the payload; with `remote`,
deployment tooling injects the provider's locator (never derived from
`ENVIRONMENT_NAME`) and the loader fetches the payload. The payload schema
belongs to the logical secret, not the backend:

- A scalar (API key, token, DSN) is a plain string in both places. Don't wrap it
  in a one-field JSON object: `DATABASE_SECRET` holds the DSN itself, never
  `{"dsn": ...}`.
- A multi-field credential is a JSON object with the same schema locally and
  remotely, declared as `Json[Model]`. If a managed store only offers a document
  (`username`, `password`, `host`, ...), model that document and build the DSN in
  the database adapter.

## Scaffold

```python
"""Credential-bearing configuration, resolved once before any client is built."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, Json, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from myservice.config.settings import (
    ConfigurationError,
    NonEmptyStr,
    describe_validation_error,
)

RequiredSecret = Annotated[SecretStr, Field(min_length=1)]
FetchSecret = Callable[[str], str]
"""Maps a provider locator to its payload; bootstrap builds it around the SDK client."""


class SecretModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ServiceAccount(SecretModel):
    username: NonEmptyStr
    password: RequiredSecret


class Secrets(SecretModel):
    database_dsn: RequiredSecret
    llm_api_key: RequiredSecret
    service_account: Json[ServiceAccount]


class SecretSources(BaseSettings):
    """Payloads when resolved from env; provider locators when remote."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    database_secret: RequiredSecret
    llm_api_key_secret: RequiredSecret
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
                "llm_api_key": _payload(sources.llm_api_key_secret, fetch),
                "service_account": _payload(sources.service_account_secret, fetch),
            }
        )
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid secrets: {describe_validation_error(exc)}") from None
```

Bootstrap selects the provider from the validated `settings.secret_provider`:
`None` for `env`, or a `FetchSecret` closure over the SDK client for `remote`.
Local development never constructs that client. Add a `Protocol` only when a
second remote backend exists. For a sync SDK called from async startup, see
`../../python-service-architecture/references/async-and-lifecycle.md` (Blocking I/O).
Resolve settings, then every secret, and only then construct clients.

For env-only secrets with no remote provider, `Secrets` can itself be a
`BaseSettings` with `RequiredSecret` fields and the same `model_config`.

## Test with a sentinel

Missing, malformed and cross-field failures must not show the payload anywhere.

```python
SENTINEL = "sentinel-7f3a"


def test_malformed_secret_is_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_SECRET", SENTINEL)
    monkeypatch.setenv("LLM_API_KEY_SECRET", SENTINEL)
    monkeypatch.setenv("SERVICE_ACCOUNT_SECRET", f'{{"username": "", "password": "{SENTINEL}"}}')

    with pytest.raises(ConfigurationError) as caught:
        load_secrets(fetch=None)

    error = caught.value
    rendered = [str(error), repr(error), str(error.__cause__), str(error.__context__)]
    assert "service_account.username" in str(error)
    assert all(SENTINEL not in text for text in rendered)
```

Also assert `SENTINEL` is absent from `repr(secrets)`, `secrets.model_dump_json()`
and captured startup logs.
