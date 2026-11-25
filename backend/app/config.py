"""Application settings loaded from environment variables / the repo-root .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: Literal["development", "test", "production"] = "development"
    DATABASE_URL: str = "postgresql+psycopg://localhost:5432/applyflow"
    TEST_DATABASE_URL: str = "postgresql+psycopg://localhost:5432/applyflow_test"
    APP_BASE_URL: str = "http://localhost:5173"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    SESSION_SECRET: str = Field(default="dev-insecure-session-secret", min_length=8)
    TOKEN_ENCRYPTION_KEYS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    ALLOWED_GOOGLE_EMAILS: Annotated[set[str], NoDecode] = Field(default_factory=set)

    WORKER_MODE: Literal["embedded", "external", "off"] = "embedded"
    GMAIL_CONCURRENCY: int = Field(default=8, ge=1, le=32)
    # Gmail allows ~50 requests/second per user (250 quota units, 5 per call); stay below it.
    GMAIL_MAX_RPS: float = Field(default=40.0, gt=0, le=50)
    LOG_LEVEL: str = "INFO"

    @field_validator("TOKEN_ENCRYPTION_KEYS", mode="before")
    @classmethod
    def _split_keys(cls, v: object) -> object:
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v

    @field_validator("ALLOWED_GOOGLE_EMAILS", mode="before")
    @classmethod
    def _split_emails(cls, v: object) -> object:
        if isinstance(v, str):
            return {e.strip().lower() for e in v.split(",") if e.strip()}
        return v

    @property
    def secure_cookies(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def effective_database_url(self) -> str:
        return self.TEST_DATABASE_URL if self.APP_ENV == "test" else self.DATABASE_URL

    def validate_runtime(self) -> None:
        """Refuse unsafe configurations (plan Complexity Tracking)."""
        if self.APP_ENV == "test":
            db_name = make_url(self.effective_database_url).database or ""
            if not db_name.endswith("_test"):
                raise RuntimeError(
                    "APP_ENV=test requires a database whose name ends in '_test' "
                    f"(got {db_name!r})."
                )
        if self.APP_ENV == "production":
            if self.SESSION_SECRET.startswith("dev-") or self.SESSION_SECRET == "change-me":
                raise RuntimeError("SESSION_SECRET must be set to a strong random value.")
            if not self.TOKEN_ENCRYPTION_KEYS:
                raise RuntimeError("TOKEN_ENCRYPTION_KEYS must be set.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
