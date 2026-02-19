"""Application settings loaded from environment variables."""

from pathlib import Path

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


settings = Settings()
