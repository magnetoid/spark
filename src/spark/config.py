from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SPARK_", extra="ignore")

    env: str = "development"
    base_url: str = "http://localhost:8000"
    secret_key: str = "change-me-in-production-please-32b"
    database_url: str = "sqlite+aiosqlite:///./spark.db"
    redis_url: str = "redis://localhost:6379/0"
    media_dir: Path = Path("./media")
    max_upload_mb: int = 50

    # AI
    anthropic_api_key: str | None = None
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "medium"

    # Email
    email_backend: str = "console"  # console | smtp | resend
    email_from: str = "Spark <noreply@example.com>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_tls: bool = True
    resend_api_key: str | None = None

    # Publishing
    publish_max_attempts: int = 3
    force_dry_run: bool = False

    # Zernio (https://docs.zernio.com) — one key connects every platform it supports
    zernio_api_key: str | None = None
    zernio_base_url: str = "https://zernio.com/api/v1"

    # Direct platform developer apps (OAuth client credentials), optional when using Zernio
    x_client_id: str | None = None
    x_client_secret: str | None = None
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    threads_app_id: str | None = None
    threads_app_secret: str | None = None
    pinterest_client_id: str | None = None
    pinterest_client_secret: str | None = None
    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
