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

    # ── Cost Configuration ──────────────────────────────────────────────────────
    COST_MULTIPLIER: float = 2.0

    # ── Wallet (NetworkChain — default for non-garage agents) ──────────────────
    WALLET_SERVICE_URL: str = "http://localhost:4001"
    WALLET_INTERNAL_API_KEY: str = ""
    MIN_BALANCE_CENTS: int = 10  # Minimum balance required to use agents ($0.10)
    MAX_DEBT_CENTS: int = 200    # $2.00 max debt — blocks agent when reached

    # ── Wallet (Garage — for garage-prefixed agents) ─────────────────────────
    GARAGE_WALLET_SERVICE_URL: str = "http://localhost:4000"
    GARAGE_WALLET_INTERNAL_API_KEY: str = ""

    # ── Agent Subscriptions ──────────────────────────────────────────────────
    AGENT_MONTHLY_COST_CENTS: int = 2400  # $24.00/month per agent
    SUBSCRIPTION_DELETE_AFTER_DAYS: int = 7  # Soft-delete 7 days after locking

    # ── Twitter ─────────────────────────────────────────────────────────────────
    TWITTER_CLIENT_ID: str = ""
    TWITTER_CLIENT_SECRET: str = ""

    # ── LinkedIn ────────────────────────────────────────────────────────────────
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""

    # ── Slack ───────────────────────────────────────────────────────────────────
    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""

    # ── GitHub ──────────────────────────────────────────────────────────────────
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # ── Trello ──────────────────────────────────────────────────────────────────
    TRELLO_CLIENT_ID: str = ""      # Trello API Key (acts as client_id in OAuth)
    TRELLO_CLIENT_SECRET: str = ""

    # ── Airtable ────────────────────────────────────────────────────────────────
    AIRTABLE_CLIENT_ID: str = ""
    AIRTABLE_CLIENT_SECRET: str = ""

    # ── Asana ───────────────────────────────────────────────────────────────────
    ASANA_CLIENT_ID: str = ""
    ASANA_CLIENT_SECRET: str = ""

    # ── ClickUp ─────────────────────────────────────────────────────────────────
    CLICKUP_CLIENT_ID: str = ""
    CLICKUP_CLIENT_SECRET: str = ""

    # ── Todoist ─────────────────────────────────────────────────────────────────
    TODOIST_CLIENT_ID: str = ""
    TODOIST_CLIENT_SECRET: str = ""

    # ── Typeform ────────────────────────────────────────────────────────────────
    TYPEFORM_CLIENT_ID: str = ""
    TYPEFORM_CLIENT_SECRET: str = ""

    # ── HubSpot ─────────────────────────────────────────────────────────────────
    HUBSPOT_CLIENT_ID: str = ""
    HUBSPOT_CLIENT_SECRET: str = ""

    # ── Notion ──────────────────────────────────────────────────────────────────
    NOTION_CLIENT_ID: str = ""
    NOTION_CLIENT_SECRET: str = ""

    # ── Stripe Connect ──────────────────────────────────────────────────────────
    STRIPE_CLIENT_ID: str = ""       # Platform's Connect client ID (ca_...)
    STRIPE_SECRET_KEY: str = ""      # Platform's secret key (sk_...) — used as client_secret

    # ── Jira ────────────────────────────────────────────────────────────────────
    JIRA_CLIENT_ID: str = ""
    JIRA_CLIENT_SECRET: str = ""

    # ── Salesforce ──────────────────────────────────────────────────────────────
    SALESFORCE_CLIENT_ID: str = ""
    SALESFORCE_CLIENT_SECRET: str = ""

    # ── Monday ──────────────────────────────────────────────────────────────────
    MONDAY_CLIENT_ID: str = ""
    MONDAY_CLIENT_SECRET: str = ""

    # ── Dropbox ─────────────────────────────────────────────────────────────────
    DROPBOX_CLIENT_ID: str = ""      # Dropbox App Key
    DROPBOX_CLIENT_SECRET: str = ""  # Dropbox App Secret

    # ── Mailchimp ───────────────────────────────────────────────────────────────
    MAILCHIMP_CLIENT_ID: str = ""
    MAILCHIMP_CLIENT_SECRET: str = ""

    # ── Calendly ────────────────────────────────────────────────────────────────
    CALENDLY_CLIENT_ID: str = ""
    CALENDLY_CLIENT_SECRET: str = ""

    # ── Pipedrive ───────────────────────────────────────────────────────────────
    PIPEDRIVE_CLIENT_ID: str = ""
    PIPEDRIVE_CLIENT_SECRET: str = ""

    # ── Confluence ──────────────────────────────────────────────────────────────
    CONFLUENCE_CLIENT_ID: str = ""   # Same Atlassian app as Jira if desired
    CONFLUENCE_CLIENT_SECRET: str = ""

    # ── Zoho CRM ────────────────────────────────────────────────────────────────
    ZOHO_CRM_CLIENT_ID: str = ""
    ZOHO_CRM_CLIENT_SECRET: str = ""

    # ── Linear ──────────────────────────────────────────────────────────────────
    LINEAR_CLIENT_ID: str = ""
    LINEAR_CLIENT_SECRET: str = ""

    # ── Box ──────────────────────────────────────────────────────────────────────
    BOX_CLIENT_ID: str = ""
    BOX_CLIENT_SECRET: str = ""

    # ── Buffer ──────────────────────────────────────────────────────────────────
    BUFFER_CLIENT_ID: str = ""
    BUFFER_CLIENT_SECRET: str = ""

    # ── Wrike ───────────────────────────────────────────────────────────────────
    WRIKE_CLIENT_ID: str = ""
    WRIKE_CLIENT_SECRET: str = ""

    # ── Eventbrite ──────────────────────────────────────────────────────────────
    EVENTBRITE_CLIENT_ID: str = ""
    EVENTBRITE_CLIENT_SECRET: str = ""

    # ── Basecamp ────────────────────────────────────────────────────────────────
    BASECAMP_CLIENT_ID: str = ""
    BASECAMP_CLIENT_SECRET: str = ""

    # ── QuickBooks ──────────────────────────────────────────────────────────────
    QUICKBOOKS_CLIENT_ID: str = ""
    QUICKBOOKS_CLIENT_SECRET: str = ""

    # ── Xero ────────────────────────────────────────────────────────────────────
    XERO_CLIENT_ID: str = ""
    XERO_CLIENT_SECRET: str = ""

    # ── WordPress ───────────────────────────────────────────────────────────────
    WORDPRESS_CLIENT_ID: str = ""
    WORDPRESS_CLIENT_SECRET: str = ""

    # ── Square ──────────────────────────────────────────────────────────────────
    SQUARE_CLIENT_ID: str = ""
    SQUARE_CLIENT_SECRET: str = ""

    # ── Microsoft (Outlook, Teams, OneDrive — shared app registration) ──────
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""

    # ── Voice Call (Telnyx + Voxtral) ───────────────────────────────────────
    # Carrier credentials — Telnyx Voice API v2 (Call Control).
    TELNYX_API_KEY: str = ""
    TELNYX_PUBLIC_KEY: str = ""          # Ed25519 public key for webhook signature verification
    TELNYX_CONNECTION_ID: str = ""       # Voice API Application ID
    TELNYX_FROM_NUMBER: str = ""         # E.164 format, e.g. "+19296959142"

    # Voxtral (Mistral) STT + TTS credentials.
    MISTRAL_API_KEY: str = ""
    VOXTRAL_VOICE_ID: str = "98559b22-62b5-4a64-a7cd-fc78ca41faa8"  # Paul (default)
    VOXTRAL_TTS_MODEL: str = "voxtral-mini-tts-2603"
    VOXTRAL_STT_MODEL: str = "voxtral-mini-2602"

    # Voice call behavior.
    VOICE_CALL_PUBLIC_URL: str = ""        # Public https/wss base URL the carrier can reach, e.g. "https://xxx.ngrok-free.dev"
    VOICE_CALL_MAX_DURATION_SEC: int = 600  # Hard cap per call
    # Silence threshold that ends a user turn (voxtral mode). 700 ms was too
    # aggressive — natural speech has pauses for breath / mid-sentence
    # thinking that exceeded that. 1500 ms tolerates conversational pauses
    # while still ending the turn promptly when the user is actually done.
    VOICE_CALL_STT_SILENCE_MS: int = 1500
    VOICE_CALL_STT_MIN_TURN_MS: int = 300   # Minimum audio before STT is triggered (voxtral mode)

    # On/off switch for Voxtral. When False, bypass the media stream entirely
    # and use Telnyx's built-in TTS (/actions/speak via Polly) and STT
    # (/actions/transcription_start via Google) — no client-side audio
    # processing. Useful for A/B testing voice quality and as a fallback
    # if Voxtral has issues. Default True to keep voxtral as the primary mode.
    VOICE_CALL_USE_VOXTRAL: bool = True
    # Polly voice id used when VOICE_CALL_USE_VOXTRAL=False. See:
    # https://developers.telnyx.com/api/call-control/CallCommandsSpeak
    VOICE_CALL_TELNYX_TTS_VOICE: str = "Polly.Joanna"
    VOICE_CALL_TELNYX_TTS_LANGUAGE: str = "en-US"
    VOICE_CALL_TELNYX_STT_LANGUAGE: str = "en"
    # Telnyx STT engine: "A" = Google (default), "B" = Telnyx's own ASR.
    VOICE_CALL_TELNYX_STT_ENGINE: str = "B"
    # Telnyx STT fires "final" events at every micro-pause, fragmenting
    # one sentence into many tiny transcripts. We aggregate fragments
    # received within this window into a single agent turn.
    VOICE_CALL_TRANSCRIPT_DEBOUNCE_MS: int = 1500


settings = Settings()
