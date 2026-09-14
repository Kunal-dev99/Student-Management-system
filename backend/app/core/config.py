"""Typed application settings, loaded once from the environment (arch §6.3, Appendix C).

No secrets in code. Local development uses `.env`; clusters use secrets/config maps.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
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

    @field_validator("database_url", "database_replica_url")
    @classmethod
    def _use_asyncpg_driver(cls, v: str | None) -> str | None:
        # Managed Postgres providers (Render, Heroku, etc.) hand out a bare
        # postgres:// or postgresql:// URL — SQLAlchemy's async engine needs the
        # +asyncpg driver suffix explicitly, so rewrite it rather than requiring
        # every deployment target to know that detail.
        if v and v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v and v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

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

    # CB-A/CB-C — the assistant is fully deterministic (fuzzy + bag-of-words). The LLM path
    # was retired in CB-C; no anthropic_api_key or assistant_llm_enabled setting is consumed.

    # Composer — the LLM composes render specs from a fixed catalog (app/modules/composer).
    # Infrastructure only: whether a tenant may *use* it is an institution setting, not env.
    # With no key the provider resolves to the mock and the composer degrades rather than
    # erroring, so a deployment without a model still boots and serves every other feature.
    llm_provider: Literal["groq", "openrouter", "mock"] = "groq"
    # Groq's catalogue moves; check /v1/models for what an account can actually reach
    # before changing this. A model the key cannot see fails at request time, not startup.
    llm_model: str = "openai/gpt-oss-120b"
    # Planning is a much easier job than composing — pick functions from a list, versus
    # design a dashboard. A smaller model halves the latency of the phase that runs two or
    # three times per question, and costs a fraction of the tokens. Set equal to llm_model
    # to use one model for both.
    llm_planner_model: str = "openai/gpt-oss-20b"
    llm_timeout_seconds: float = 45.0
    groq_api_key: str | None = None

    # OpenRouter — an alternative to Groq for deployments without a Groq key. Uses
    # OpenRouter's free-tier model catalogue (":free" suffix), so this can run at
    # zero API cost. Free models are rate-limited and occasionally retired by
    # OpenRouter — check https://openrouter.ai/models?max_price=0 if the default
    # model 404s. Selected via LLM_PROVIDER=openrouter; ignored otherwise.
    openrouter_api_key: str | None = None
    # Verified 2026-09-13 against OpenRouter's live free catalogue: llama-3.1-8b-instruct
    # was retired from the free tier: OpenRouter now redirects it to a paid slug (404).
    # The Google Gemma free models are rate-limited hard on the shared pool (429 on
    # nearly every call). Nemotron's reasoning model was the one that reliably returned
    # valid JSON across repeated calls — pick it, but check
    # https://openrouter.ai/models?max_price=0 if this one also gets retired or
    # rate-limited later; free-tier availability rotates.
    openrouter_model: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    openrouter_planner_model: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    # OpenRouter asks integrations to identify themselves (used for their public
    # rankings page, not required for the API to function).
    openrouter_site_url: str = "https://pgr-platform.local"
    openrouter_site_name: str = "PGR Platform"

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
