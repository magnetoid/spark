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
    # Built React app (frontend/dist), served at spa_base ("/" = the app owns every path no
    # other route claims). Missing directory = the app simply is not served (API-only, tests).
    spa_dir: Path = Path("frontend/dist")
    spa_base: str = "/"

    # Everyone who signs in with a password must use two-factor (Settings → Brand & team)
    require_two_factor: bool = False

    # AI
    anthropic_api_key: str | None = None
    # Janus agent (github.com/magnetoid/Janus-Agent), deployed next to Spark; see deploy/janus
    janus_base_url: str | None = None
    janus_api_key: str | None = None
    janus_managed: bool = (
        False  # true in the compose stack: the `janus` service is wired in, Spark pushes its config
    )
    janus_model: str | None = None  # defaults to ai_model
    janus_effort: str = "medium"
    janus_approvals: str = "manual"
    janus_soul: str | None = None  # the personality; the built-in text when empty
    janus_extra_yaml: str | None = None  # merged over the configuration Spark writes
    janus_update_webhook: str | None = (
        None  # external installs only: a deploy hook that rebuilds Janus
    )
    janus_update_token: str | None = None
    # Image generation (Claude makes no images): OpenAI's image model behind the "Image generation" connector
    openai_api_key: str | None = None
    image_model: str = (
        "gpt-image-2.6-flare"  # see services/images.py: retired IDs fall back to this
    )
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "medium"
    ai_model_fast: str = "claude-haiku-5-5"  # labels and other quick, cheap calls

    # Email
    email_backend: str = "console"  # console | smtp | resend
    email_from: str = "Spark <noreply@example.com>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_tls: bool = True
    resend_api_key: str | None = None

    # Chat notifications (Settings → Connectors → Chat notifications); any one destination is enough
    chat_slack_webhook: str | None = None  # Slack or Mattermost incoming webhook
    chat_discord_webhook: str | None = None
    chat_teams_webhook: str | None = (
        None  # a Teams Workflows "when a webhook request is received" URL
    )
    chat_telegram_token: str | None = None
    chat_telegram_chat_id: str | None = None
    chat_on_approval: bool = True
    chat_on_failed: bool = True
    chat_on_review: bool = True
    chat_on_published: bool = False
    chat_on_channel: bool = True

    # Publishing
    publish_max_attempts: int = 3
    force_dry_run: bool = False

    # Zernio (https://docs.zernio.com) — one key connects every platform it supports
    zernio_api_key: str | None = None
    zernio_base_url: str = "https://zernio.com/api/v1"
    # Secret Zernio signs webhook deliveries with; derived from secret_key when unset
    zernio_webhook_secret: str | None = None

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
