"""Typed application settings, loaded once from the environment (arch §6.3, Appendix C).

No secrets in code. Local development uses `.env`; clusters use secrets/config maps.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["dev", "staging", "production"] = "dev"
    app_secret_key: str = "change-me-in-prod"

    # Default to async SQLite so the app boots locally without a Postgres instance.
    # Production sets DATABASE_URL to postgresql+asyncpg://...
    database_url: str = "sqlite+aiosqlite:///./pgr_dev.db"
    database_replica_url: str | None = None

    redis_url: str | None = None
    broker_url: str | None = None

    object_store_endpoint: str | None = None
    object_store_bucket: str | None = None
    # Phase 4A.2 — file storage. "local" writes under storage_root; "s3" is a later swap.
    storage_backend: Literal["local", "s3"] = "local"
    storage_root: str = "./var/storage"
    max_upload_mb: int = 50

    # Phase 4A.3 — email. "console" logs the message (dev); "smtp" sends via aiosmtplib (prod).
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    email_from: str = "PGR Platform <no-reply@pgr.local>"
    app_base_url: str = "http://localhost:3000"  # for links in emails (password reset, etc.)

    # Phase 4A.1 — background worker cadence (seconds).
    worker_scheduler_interval_seconds: int = 60
    worker_dispatch_interval_seconds: int = 20
    worker_notify_interval_seconds: int = 30
    outbox_max_attempts: int = 5

    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1_209_600
    # Phase 4A.4 — auth hardening.
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    password_reset_ttl_seconds: int = 3600

    integration_finance_url: str | None = None
    integration_research_url: str | None = None
    integration_hr_url: str | None = None

    # Phase 5 — assistant. The rule-based intent parser is the primary path and needs nothing.
    # The model fallback is OPT-IN: it only runs when assistant_llm_enabled is true AND a key is
    # set. Leaving it off keeps every query on-premise (no student data sent to a third party).
    assistant_llm_enabled: bool = False
    anthropic_api_key: str | None = None

    sentry_dsn: str | None = None
    otel_exporter_endpoint: str | None = None
    log_level: Literal["info", "debug", "warning"] = "info"

    api_v1_prefix: str = "/api/v1"

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    return Settings()
