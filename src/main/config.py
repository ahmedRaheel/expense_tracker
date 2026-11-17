from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:postgres123@localhost:5432/expenses"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=32, default="LOCAL_DEV_ONLY_CHANGE_THIS_LONG_SECRET_NOW")
    jwt_algorithm: str = "HS256"
    access_ttl_seconds: int = 900
    refresh_ttl_seconds: int = 604800
    storage_endpoint_url: str | None = "http://localhost:9000"
    storage_public_endpoint_url: str | None = None
    storage_bucket: str = "expense-receipts"
    storage_region: str = "us-east-1"
    storage_access_key: str | None = None
    storage_secret_key: str | None = None
    import_spool_dir: str = ".data/imports"
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
