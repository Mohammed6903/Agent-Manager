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
    ROOT_PATH: str = "/agents"  # Set when behind a reverse proxy with a path prefix
    MAX_UPLOAD_SIZE_MB: int = 5  # Target max size after compression (in MB)
    MAX_RAW_UPLOAD_SIZE_MB: int = 20  # Maximum raw upload size before compression (in MB)
    GMAIL_SERVICE_URL: str = "https://openclaw.marketsverse.com/gmail-auth"
    GARAGE_API_URL: str = "http://localhost:4000"


settings = Settings()
