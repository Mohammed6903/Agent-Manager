import time
import httpx
from datetime import datetime, timezone
import logging

from .base import BaseAuthHandler

logger = logging.getLogger(__name__)

class OAuth2Handler(BaseAuthHandler):
    """
    Standard HTTP-based OAuth2 Handler (Not for use with Google SDKs).
    Automatically refreshes access tokens if expired.
    """
    
    def inject(self, creds: dict, headers: dict, params: dict, method: str, url: str) -> tuple[dict, dict]:
        token = creds.get(self.scheme.get("token_field", "access_token"))
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        self._inject_extra_headers(creds, headers)
        return headers, params

    def requires_refresh(self, creds: dict) -> bool:
        """Check if current UTC time has passed the 'expires_at' timestamp string."""
        expires_at_str = creds.get("expires_at")
        if not expires_at_str:
            return False
            
        try:
            expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
            # Add a 60 second buffer to refresh *before* it actually expires mid-flight
            now = datetime.now(timezone.utc)
            return (expires_at.timestamp() - 60) < now.timestamp()
        except (ValueError, TypeError):
            return False

    async def refresh(self, creds: dict, db) -> dict:
        """Execute the OAuth2 token refresh flow."""
        refresh_token = creds.get("refresh_token")
        token_url = creds.get("token_url") or self.scheme.get("token_url")
        client_id = creds.get("client_id") or self.scheme.get("client_id")
        client_secret = creds.get("client_secret") or self.scheme.get("client_secret")
        
        if not all([refresh_token, token_url, client_id, client_secret]):
            logger.warning("OAuth2 credentials missing required fields to perform refresh. Skipping refresh attempt.")
            return creds

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=data)
            resp.raise_for_status()
            
            payload = resp.json()

        # Update creds dictionary
        if "access_token" in payload:
            creds["access_token"] = payload["access_token"]
            
        # Often refresh tokens are rolling
        if "refresh_token" in payload:
            creds["refresh_token"] = payload["refresh_token"]
            
        if "expires_in" in payload:
             # Calculate new expires_at ISO 8601 string
             now = datetime.now(timezone.utc)
             new_expire_time = now.timestamp() + float(payload["expires_in"])
             new_dt = datetime.fromtimestamp(new_expire_time, tz=timezone.utc)
             creds["expires_at"] = new_dt.isoformat()

        return creds
