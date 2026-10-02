from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    """Resolved once in the composition root; values go only to the constructors that need them."""

    model_config = SettingsConfigDict(frozen=True, hide_input_in_errors=True)

    database_dsn: SecretStr
