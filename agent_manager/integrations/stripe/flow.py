"""Stripe Connect OAuth 2.0 flow for Standard accounts.

Stripe Connect has a non-standard OAuth flow:
- The platform's Secret Key (sk_...) is used as client_secret in token exchange
- The token response includes stripe_user_id (the connected account ID)
- The connected account's access_token is used as Bearer for API calls
- Refresh tokens rotate the access_token via Stripe's deauthorize/re-auth flow
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ..auth.oauth2_flow import OAuth2FlowProvider
from ...services.secret_service import SecretService
from ...config import settings

logger = logging.getLogger(__name__)

STRIPE_AUTHORIZE_URL = "https://connect.stripe.com/oauth/authorize"
STRIPE_TOKEN_URL = "https://connect.stripe.com/oauth/token"
STRIPE_DEAUTHORIZE_URL = "https://connect.stripe.com/oauth/deauthorize"
REDIRECT_URI_PATH = "/api/integrations/oauth/callback/stripe"


class StripeConnectOAuth2Flow(OAuth2FlowProvider):
    """OAuth 2.0 authorization code flow for Stripe Connect (Standard accounts)."""

    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        state = f"{agent_id}|{integration_name}"
        params = {
            "response_type": "code",
            "client_id": settings.STRIPE_CLIENT_ID,
            "scope": "read_write",
            "redirect_uri": f"{settings.SERVER_URL}{REDIRECT_URI_PATH}",
            "state": state,
        }
        return f"{STRIPE_AUTHORIZE_URL}?{urlencode(params)}"

    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str,
        **kwargs,
    ) -> dict:
        # Exchange authorization code for access token + stripe_user_id
        data = {
            "grant_type": "authorization_code",
            "code": code,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    STRIPE_TOKEN_URL,
                    data=data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}",
                    },
                )
                resp.raise_for_status()
                token_data = resp.json()
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Stripe Connect OAuth token exchange failed: {e}",
            )

        # Build credentials dict
        # Stripe Connect returns: access_token, refresh_token, token_type,
        # stripe_publishable_key, stripe_user_id, scope
        creds = {
            "access_token": token_data["access_token"],
            "token_type": token_data.get("token_type", "bearer"),
            "scope": token_data.get("scope", ""),
            "stripe_user_id": token_data["stripe_user_id"],
            "stripe_publishable_key": token_data.get("stripe_publishable_key", ""),
            # For token refresh, Stripe uses the platform secret key
            "token_url": STRIPE_TOKEN_URL,
            "client_id": settings.STRIPE_CLIENT_ID,
            "client_secret": settings.STRIPE_SECRET_KEY,
        }

        if "refresh_token" in token_data:
            creds["refresh_token"] = token_data["refresh_token"]

        # Stripe Connect tokens don't have expires_in — they are long-lived
        # but can be refreshed. Set no expiry so OAuth2Handler won't force-refresh.

        # Store credentials (encrypted)
        SecretService.set_secret(db, agent_id, integration_name, creds)

        # Build metadata from the connected account
        user_metadata = {}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.stripe.com/v1/accounts/{token_data['stripe_user_id']}",
                    headers={"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"},
                )
                if resp.status_code == 200:
                    account = resp.json()
                    if account.get("business_profile", {}).get("name"):
                        user_metadata["name"] = account["business_profile"]["name"]
                    elif account.get("settings", {}).get("dashboard", {}).get("display_name"):
                        user_metadata["name"] = account["settings"]["dashboard"]["display_name"]
                    if account.get("email"):
                        user_metadata["email"] = account["email"]
        except Exception as e:
            logger.warning(f"Failed to fetch Stripe connected account info: {e}")

        return {
            "status": "authorized",
            "agent_id": agent_id,
            "integration": integration_name,
            "metadata": user_metadata or None,
        }
