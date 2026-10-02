from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    default_records: int = 100
    max_records: int = 1000
