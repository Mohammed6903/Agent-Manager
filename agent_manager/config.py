"""Application settings loaded from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the project root (one level above agent_manager/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENCLAW_GATEWAY_URL: str = "http://localhost:18789"
    OPENCLAW_GATEWAY_TOKEN: str = ""
    OPENCLAW_STATE_DIR: str = "/root/.openclaw"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    SERVER_URL: str = "http://localhost:8000"
    ROOT_PATH: str = "/"  # Set when behind a reverse proxy with a path prefix
    MAX_UPLOAD_SIZE_MB: int = 5  # Target max size after compression (in MB)
    MAX_RAW_UPLOAD_SIZE_MB: int = 20  # Maximum raw upload size before compression (in MB)
    GARAGE_API_URL: str = "http://localhost:4000"
    GARAGE_CHAT_INTERNAL_URL: str = "http://localhost:3000"
    GARAGE_INTERNAL_API_KEY: str = ""

    # ── Database ────────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://localhost/openclaw"

    # ── AWS S3 ──────────────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: str = ""

    # ── Redis / Celery ──────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Embeddings ───────────────────────────────────────────────────────────────
    # Provider must be "openai" or "gemini"; the corresponding API key is required.
    EMBEDDING_PROVIDER: Literal["openai", "gemini"] = "openai"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    @model_validator(mode="after")
    def _validate_embedding_keys(self) -> "Settings":
        """Raise at startup if the selected provider's API key is missing."""
        if self.EMBEDDING_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai"
            )
        if self.EMBEDDING_PROVIDER == "gemini" and not self.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini"
            )
        return self

    # ── Qdrant ──────────────────────────────────────────────────────────────────
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # ── Encryption ──────────────────────────────────────────────────────────────
    FERNET_KEY: str = ""


    # ── Twitter ─────────────────────────────────────────────────────────────────
    TWITTER_CLIENT_ID: str = ""
    TWITTER_CLIENT_SECRET: str = ""

    # ── LinkedIn ────────────────────────────────────────────────────────────────
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""


settings = Settings()
