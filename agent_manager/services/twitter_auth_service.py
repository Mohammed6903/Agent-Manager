"""Twitter OAuth 1.0a authentication service."""

import logging
from urllib.parse import parse_qsl

import httpx
from oauthlib.oauth1 import Client

from ..config import settings

logger = logging.getLogger(__name__)

REQUEST_TOKEN_URL = "https://api.twitter.com/oauth/request_token"
AUTHORIZATION_URL = "https://api.twitter.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://api.twitter.com/oauth/access_token"
REDIRECT_URI = f"{settings.SERVER_URL}/api/integrations/oauth/callback/twitter"


async def get_request_token(state: str) -> tuple[str, str, str]:
    """Obtain an OAuth 1.0a request token from Twitter.
    
    Returns:
        Tuple of (auth_url, request_token, request_token_secret).
    """
    client = Client(
        client_key=settings.TWITTER_API_KEY,
        client_secret=settings.TWITTER_API_SECRET,
        callback_uri=f"{REDIRECT_URI}?state={state}",  # Pass state via callback query param for OAuth1
    )
    uri, headers, body = client.sign(REQUEST_TOKEN_URL, http_method="POST")
    
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.post(uri, headers=headers)
        resp.raise_for_status()
        
    credentials = dict(parse_qsl(resp.text))
    request_token = credentials.get("oauth_token")
    request_token_secret = credentials.get("oauth_token_secret")
    
    auth_url = f"{AUTHORIZATION_URL}?oauth_token={request_token}"
    return auth_url, request_token, request_token_secret


async def exchange_verifier(request_token: str, request_token_secret: str, oauth_verifier: str) -> dict:
    """Exchange the OAuth 1.0a verifier for final user access tokens.
    
    Returns:
        Dict with access_token, access_token_secret, user_id, screen_name.
    """
    client = Client(
        client_key=settings.TWITTER_API_KEY,
        client_secret=settings.TWITTER_API_SECRET,
        resource_owner_key=request_token,
        resource_owner_secret=request_token_secret,
        verifier=oauth_verifier,
    )
    uri, headers, body = client.sign(ACCESS_TOKEN_URL, http_method="POST")
    
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.post(uri, headers=headers)
        resp.raise_for_status()
        
    credentials = dict(parse_qsl(resp.text))
    
    return {
        "access_token": credentials.get("oauth_token"),
        "access_token_secret": credentials.get("oauth_token_secret"),
        "user_id": credentials.get("user_id"),
        "screen_name": credentials.get("screen_name"),
    }
