"""Notion OAuth 2.0 flow.

Notion's token exchange uses HTTP Basic Auth (base64(client_id:client_secret))
instead of form-encoded client credentials. The token response also includes
workspace metadata (workspace_id, workspace_name, workspace_icon, bot_id).
"""

import base64
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ..auth.oauth2_flow import OAuth2FlowProvider
from ...services.secret_service import SecretService
from ...config import settings

logger = logging.getLogger(__name__)

NOTION_AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"


class NotionOAuth2Flow(OAuth2FlowProvider):
    """OAuth 2.0 authorization code flow for Notion Public Integrations."""

    @property
    def redirect_uri(self) -> str:
        return f"{settings.SERVER_URL}/api/integrations/oauth/callback/notion"

    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        from urllib.parse import urlencode
        state = f"{agent_id}|{integration_name}"
        params = {
            "client_id": settings.NOTION_CLIENT_ID,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        return f"{NOTION_AUTHORIZE_URL}?{urlencode(params)}"

    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str,
        **kwargs,
    ) -> dict:
        # Notion requires Basic Auth for token exchange
        basic_token = base64.b64encode(
            f"{settings.NOTION_CLIENT_ID}:{settings.NOTION_CLIENT_SECRET}".encode()
        ).decode()

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    NOTION_TOKEN_URL,
                    json=data,
                    headers={
                        "Authorization": f"Basic {basic_token}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                token_data = resp.json()
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Notion OAuth2 token exchange failed: {e}",
            )

        # Build credentials — Notion tokens don't expire (no refresh_token)
        creds = {
            "access_token": token_data["access_token"],
            "token_type": token_data.get("token_type", "bearer"),
            "bot_id": token_data.get("bot_id", ""),
            "workspace_id": token_data.get("workspace_id", ""),
            "workspace_name": token_data.get("workspace_name", ""),
        }

        # Store credentials (encrypted)
        SecretService.set_secret(db, agent_id, integration_name, creds)

        # Build metadata
        user_metadata = {}
        if token_data.get("workspace_name"):
            user_metadata["name"] = token_data["workspace_name"]
        if token_data.get("workspace_icon"):
            user_metadata["picture"] = token_data["workspace_icon"]
        if token_data.get("owner", {}).get("user", {}).get("name"):
            user_metadata["name"] = token_data["owner"]["user"]["name"]
        if token_data.get("owner", {}).get("user", {}).get("avatar_url"):
            user_metadata["picture"] = token_data["owner"]["user"]["avatar_url"]

        return {
            "status": "authorized",
            "agent_id": agent_id,
            "integration": integration_name,
            "metadata": user_metadata or None,
        }
