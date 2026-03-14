import logging
import base64
import hashlib
import os
import time

from sqlalchemy.orm import Session
from fastapi import HTTPException, Request
from urllib.parse import urlencode

from .oauth2_flow import OAuth2FlowProvider
from ...services.secret_service import SecretService
from ...config import settings
import httpx

logger = logging.getLogger(__name__)


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge."""
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
    code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


class TwitterOAuth2Flow(OAuth2FlowProvider):
    """OAuth 2.0 flow for Twitter / X with PKCE."""
    
    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        code_verifier, code_challenge = generate_pkce_pair()
        state = f"{agent_id}|{integration_name}"
        
        # We need to temporarily store the code_verifier so we can use it during the callback
        if db:
            SecretService.set_secret(
                db, 
                agent_id, 
                f"_twitter_pkce_{agent_id}", 
                {"code_verifier": code_verifier}
            )

        # Scopes required for the SDK endpoints
        scopes = "tweet.read tweet.write users.read offline.access dm.read dm.write"
        redirect_uri = f"{settings.SERVER_URL}/api/integrations/oauth/callback/twitter"
        
        params = {
            "response_type": "code",
            "client_id": settings.TWITTER_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }
        
        url = f"https://twitter.com/i/oauth2/authorize?{urlencode(params)}"
        return url

    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str,
        request: Request = None,
    ) -> dict:
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")

        # 1. Retrieve the code_verifier from the DB
        temp_secret_name = f"_twitter_pkce_{agent_id}"
        temp_creds = SecretService.get_secret(db, agent_id, temp_secret_name)
        
        if not temp_creds or "code_verifier" not in temp_creds:
            logger.error(f"Could not find temporary OAuth 2.0 PKCE verifier for agent {agent_id}")
            raise HTTPException(status_code=400, detail="Twitter auth session expired or invalid. Please try again.")

        code_verifier = temp_creds["code_verifier"]

        # 2. Exchange code for access tokens
        redirect_uri = f"{settings.SERVER_URL}/api/integrations/oauth/callback/twitter"
        token_url = "https://api.twitter.com/2/oauth2/token"
        
        # Twitter OAuth2 uses Basic Auth with client_id:client_secret for confidential clients
        auth = (str(settings.TWITTER_CLIENT_ID), str(settings.TWITTER_CLIENT_SECRET))
        
        payload = {
            "code": code,
            "grant_type": "authorization_code",
            "client_id": str(settings.TWITTER_CLIENT_ID),
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(token_url, data=payload, auth=auth, headers=headers)
                resp.raise_for_status()
                tokens = resp.json()
        except Exception as e:
            logger.error(f"Failed to exchange Twitter OAuth 2.0 code: {e}")
            raise HTTPException(status_code=400, detail="Failed to get Twitter access token")

        # 3. Store final tokens for the integration
        if "expires_in" in tokens:
            tokens["expires_at"] = int(time.time()) + int(tokens["expires_in"])
            
        string_tokens = {k: str(v) for k, v in tokens.items() if v is not None}
        SecretService.set_secret(db, agent_id, integration_name, string_tokens)

        # 4. Clean up temporary PKCE info
        SecretService.delete_secret(db, agent_id, temp_secret_name)

        # 5. Fetch user profile metadata
        user_metadata = {}
        try:
            async with httpx.AsyncClient() as client:
                me_resp = await client.get(
                    "https://api.twitter.com/2/users/me",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                    params={"user.fields": "profile_image_url"}
                )
                if me_resp.status_code == 200:
                    user_data = me_resp.json().get("data", {})
                    if user_data.get("name"):
                        user_metadata["name"] = user_data["name"]
                    if user_data.get("username"):
                        user_metadata["username"] = user_data["username"]
                    if user_data.get("profile_image_url"):
                        user_metadata["picture"] = user_data["profile_image_url"]
        except Exception as e:
            logger.warning(f"Failed to fetch Twitter user info during callback: {e}")

        return {
            "status": "authorized", 
            "agent_id": agent_id, 
            "integration": integration_name,
            "metadata": user_metadata if user_metadata else None
        }

