"""Generic OAuth 2.0 Authorization Code flow for third-party integrations.

Each integration supplies its own OAuth config (URLs, scopes, client creds).
This module provides a reusable flow factory so integrations only need to
define a config dict — no per-integration flow.py boilerplate required.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .oauth2_flow import OAuth2FlowProvider
from ...services.secret_service import SecretService

logger = logging.getLogger(__name__)


class GenericOAuth2Config:
    """Configuration for a standard OAuth 2.0 Authorization Code integration."""

    def __init__(
        self,
        provider_name: str,
        authorize_url: str,
        token_url: str,
        client_id_setting: str,
        client_secret_setting: str,
        scopes: list[str],
        *,
        extra_authorize_params: dict | None = None,
        userinfo_url: str | None = None,
        userinfo_headers: dict | None = None,
    ):
        self.provider_name = provider_name
        self.authorize_url = authorize_url
        self.token_url = token_url
        self.client_id_setting = client_id_setting
        self.client_secret_setting = client_secret_setting
        self.scopes = scopes
        self.extra_authorize_params = extra_authorize_params or {}
        self.userinfo_url = userinfo_url
        self.userinfo_headers = userinfo_headers or {}

    @property
    def client_id(self) -> str:
        from ...config import settings
        return getattr(settings, self.client_id_setting, "")

    @property
    def client_secret(self) -> str:
        from ...config import settings
        return getattr(settings, self.client_secret_setting, "")

    @property
    def redirect_uri(self) -> str:
        from ...config import settings
        return f"{settings.SERVER_URL}/api/integrations/oauth/callback/{self.provider_name}"


class GenericOAuth2Flow(OAuth2FlowProvider):
    """Reusable OAuth 2.0 flow backed by a GenericOAuth2Config."""

    def __init__(self, config: GenericOAuth2Config):
        self.config = config

    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        state = f"{agent_id}|{integration_name}"
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
            **self.config.extra_authorize_params,
        }
        return f"{self.config.authorize_url}?{urlencode(params)}"

    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str,
        **kwargs,
    ) -> dict:
        # Exchange code for tokens
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.config.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded",
                             "Accept": "application/json"},
                )
                resp.raise_for_status()
                token_data = resp.json()
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"{self.config.provider_name} OAuth2 token exchange failed: {e}",
            )

        # Build credentials dict
        creds = {
            "access_token": token_data["access_token"],
            "token_type": token_data.get("token_type", "bearer"),
            "scope": token_data.get("scope", ""),
            "token_url": self.config.token_url,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }

        if "refresh_token" in token_data:
            creds["refresh_token"] = token_data["refresh_token"]

        if "expires_in" in token_data:
            expires_at = datetime.now(timezone.utc).timestamp() + float(token_data["expires_in"])
            creds["expires_at"] = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()

        # Store credentials (encrypted)
        SecretService.set_secret(db, agent_id, integration_name, creds)

        # Optionally fetch user profile for metadata
        user_metadata = {}
        if self.config.userinfo_url:
            try:
                headers = {
                    "Authorization": f"Bearer {token_data['access_token']}",
                    **self.config.userinfo_headers,
                }
                async with httpx.AsyncClient() as client:
                    resp = await client.get(self.config.userinfo_url, headers=headers)
                    if resp.status_code == 200:
                        profile = resp.json()
                        # Common fields across providers
                        for key in ("email", "name", "login", "username", "display_name"):
                            if key in profile and profile[key]:
                                mapped = "name" if key in ("login", "username", "display_name") else key
                                user_metadata.setdefault(mapped, profile[key])
                        # Avatar / picture
                        for key in ("avatar_url", "picture", "photo", "profile_image_url"):
                            if key in profile and profile[key]:
                                user_metadata.setdefault("picture", profile[key])
                                break
            except Exception as e:
                logger.warning(f"Failed to fetch user info for {self.config.provider_name}: {e}")

        return {
            "status": "authorized",
            "agent_id": agent_id,
            "integration": integration_name,
            "metadata": user_metadata or None,
        }
