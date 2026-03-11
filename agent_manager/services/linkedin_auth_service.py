"""LinkedIn OAuth 2.0 authentication service."""

import logging
from urllib.parse import urlencode

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REDIRECT_URI = f"{settings.SERVER_URL}/api/integrations/oauth/callback/linkedin"

# Scopes for LinkedIn OAuth 2.0
DEFAULT_SCOPES = [
    "openid",
    "profile",
    "email",
    "w_member_social",
]


def get_auth_url(state: str) -> str:
    """Build the LinkedIn OAuth 2.0 authorization URL."""
    params = {
        "response_type": "code",
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(DEFAULT_SCOPES),
        "state": state,
    }
    
    return f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for an access token.
    
    Returns:
        Dict with access_token, expires_in, scope, token_type.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "client_secret": settings.LINKEDIN_CLIENT_SECRET,
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            LINKEDIN_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()
