"""LinkedIn OAuth 2.0 authentication service."""
import logging
from urllib.parse import urlencode
import httpx
from ...config import settings

logger = logging.getLogger(__name__)

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REDIRECT_URI = f"{settings.SERVER_URL}/api/integrations/oauth/callback/linkedin"

# Scopes for LinkedIn OAuth 2.0.
# r_network is a restricted scope — only included if the app has been granted
# access by LinkedIn. Remove it if your app hasn't been approved, or the auth
# URL will silently drop unrecognized scopes and connections calls will 403.
DEFAULT_SCOPES = [
    "openid",
    "profile",
    "w_member_social",
]

# Optional — only request if LinkedIn has approved r_network for your app.
NETWORK_SCOPES = DEFAULT_SCOPES + ["r_network"]


def get_auth_url(state: str, include_network_scope: bool = False) -> str:
    """Build the LinkedIn OAuth 2.0 authorization URL.

    Args:
        state: Opaque state string passed through the OAuth round-trip.
        include_network_scope: Set True only if your LinkedIn app has been
            approved for the r_network restricted permission. Requesting it
            without approval causes LinkedIn to silently ignore or reject it.
    """
    scopes = NETWORK_SCOPES if include_network_scope else DEFAULT_SCOPES
    params = {
        "response_type": "code",
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(scopes),
        "state": state,
    }
    return f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for an access token.

    Returns:
        Dict with access_token, expires_in, scope, token_type, and optionally
        refresh_token / refresh_token_expires_in.
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
        # TEMP DEBUG — remove after fixing
        logger.error("LinkedIn token exchange status: %s", resp.status_code)
        logger.error("LinkedIn token exchange body: %s", resp.text)
        logger.error("LinkedIn redirect_uri sent: %s", REDIRECT_URI)
        resp.raise_for_status()
        return resp.json()
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Exchange a refresh token for a new access token.

    LinkedIn only issues refresh tokens when the r_emailaddress scope (or
    certain partner scopes) are approved, and only for apps using the
    token refresh flow. If your app does not receive refresh tokens this
    function will raise — callers should catch and prompt re-auth.

    Returns:
        Dict with access_token, expires_in, refresh_token,
        refresh_token_expires_in, scope, token_type.
    """
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
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