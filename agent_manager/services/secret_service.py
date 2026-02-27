"""Secret Service — fetches agent secrets directly from the database."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models.gmail import AgentSecret
from ..security import decrypt

logger = logging.getLogger("agent_manager.services.secret_service")


class SecretService:
    """Thin wrapper around the agent_secrets table for reading secrets."""

    @staticmethod
    def _decrypt_secret_data(data: dict[str, Any]) -> dict[str, str]:
        """Decrypt every value in the dict with Fernet."""
        return {k: decrypt(str(v)) for k, v in data.items()}

    @staticmethod
    def get_secret(db: Session, agent_id: str, service_name: str) -> dict | None:
        """Return decrypted secret_data for the given agent + service, or None."""
        secret = (
            db.query(AgentSecret)
            .filter(
                AgentSecret.agent_id == agent_id,
                AgentSecret.service_name == service_name,
            )
            .first()
        )
        if not secret:
            return None

        try:
            return SecretService._decrypt_secret_data(secret.secret_data)
        except Exception as exc:
            logger.warning(
                "Failed to decrypt secret '%s' for agent '%s': %s",
                service_name, agent_id, exc,
            )
            return None
