"""Typed configuration, loaded once from environment variables.

Adapted from orkiza-captacion's settings pattern. See .env.example at repo root.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment variables for VirtualOS. See .env.example for reference."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- Environment ----------
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ---------- Postgres (Supabase session pooler) ----------
    database_url: str = Field(..., description="Postgres connection string (session pooler)")

    # ---------- Supabase ----------
    supabase_url: str | None = None
    supabase_anon_key: SecretStr | None = None
    supabase_service_key: SecretStr | None = None
    # Legacy HS256 secret; if unset, JWT verification uses the project's JWKS endpoint.
    supabase_jwt_secret: SecretStr | None = None

    # ---------- LLM ----------
    llm_provider: Literal["anthropic", "openai"] = "anthropic"

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _lower_provider(cls, v: object) -> object:
        return v.lower() if isinstance(v, str) else v

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    # Fast model: hooks/grouping. Strong model: ideas/brief/agent. IDs configurable per env.
    llm_model_fast: str = "claude-haiku-4-5"
    llm_model_strong: str = "claude-sonnet-4-6"
    anthropic_prompt_cache_enabled: bool = True

    # ---------- Apify ----------
    apify_token: SecretStr | None = None
    apify_webhook_secret: SecretStr | None = None
    apify_actor_tiktok_trends: str = "lexis-solutions/tiktok-trending-hashtags-scraper"
    apify_actor_tiktok_profiles: str = "clockworks/tiktok-scraper"
    apify_actor_instagram_profiles: str = "apify/instagram-scraper"

    # ---------- News (Serper -> DDG fallback) ----------
    serper_api_key: str = ""
    serper_gl: str = "co"
    serper_hl: str = "es"

    # ---------- Raw storage ----------
    s3_bucket: str | None = None
    aws_region: str = "us-east-1"
    raw_data_dir: str = ".data/raw"

    # ---------- API ----------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # OpenAI equivalents used when llm_provider=openai but the model ids are Claude's.
    openai_model_fast: str = "gpt-5.4-mini"
    openai_model_strong: str = "gpt-5.4"

    @property
    def resolved_model_fast(self) -> str:
        if self.llm_provider == "openai" and "claude" in self.llm_model_fast:
            return self.openai_model_fast
        return self.llm_model_fast

    @property
    def resolved_model_strong(self) -> str:
        if self.llm_provider == "openai" and "claude" in self.llm_model_strong:
            return self.openai_model_strong
        return self.llm_model_strong

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton — load once per process."""
    return Settings()  # type: ignore[call-arg]
