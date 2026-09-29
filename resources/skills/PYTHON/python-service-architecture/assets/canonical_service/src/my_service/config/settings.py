from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    default_records: int = 100
    max_records: int = 1000
