import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from fastapi import HTTPException

from .oauth2_flow import OAuth2FlowProvider
from ...services.secret_service import SecretService
from ...services.linkedin_auth_service import get_auth_url, exchange_code

logger = logging.getLogger(__name__)


class LinkedInOAuth2Flow(OAuth2FlowProvider):
    """OAuth 2.0 authorization code flow for LinkedIn."""

    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        composite_state = f"{agent_id}|{integration_name}"
        return get_auth_url(state=composite_state)

    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str,
    ) -> dict:
        try:
            token_data = await exchange_code(code)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"LinkedIn OAuth2 token exchange failed: {str(e)}")

        # Build credentials dict for SecretService
        creds = {
            "access_token": token_data["access_token"],
            "token_type": token_data.get("token_type", "bearer"),
            "scope": token_data.get("scope", ""),
            "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        }

        if "refresh_token" in token_data:
            creds["refresh_token"] = token_data["refresh_token"]

        if "expires_in" in token_data:
            expires_at = datetime.now(timezone.utc).timestamp() + float(token_data["expires_in"])
            creds["expires_at"] = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()

        # Store credentials
        SecretService.set_secret(db, agent_id, integration_name, creds)

        return {"status": "authorized", "agent_id": agent_id, "integration": integration_name}
