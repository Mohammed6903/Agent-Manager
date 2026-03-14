"""LinkedIn operations service."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
import httpx

from .secret_service import SecretService
from .linkedin_auth_service import refresh_access_token
from ..integrations.sdk_logger import log_integration_call

from urllib.parse import unquote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_urn(value: str, urn_type: str) -> str:
    """Ensure value is a full URN, never double-wrapping it.

    Examples:
        _normalize_urn("abc123", "person")  -> "urn:li:person:abc123"
        _normalize_urn("urn:li:person:abc123", "person") -> "urn:li:person:abc123"
    """
    prefix = f"urn:li:{urn_type}:"
    return value if value.startswith(prefix) else f"{prefix}{value}"


async def _maybe_refresh_creds(db: Session, agent_id: str, creds: dict) -> dict:
    """Refresh the access token if it has expired (or is about to, within 60s).

    If no refresh_token is stored, or the refresh call fails, returns the
    original creds unchanged — the subsequent API call will surface the 401
    and the caller can prompt the user to re-authenticate.
    """
    expires_at_raw = creds.get("expires_at")
    if not expires_at_raw:
        return creds

    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        return creds

    now = datetime.now(timezone.utc)
    # Refresh if within 60 seconds of expiry
    if (expires_at - now).total_seconds() > 60:
        return creds

    refresh_token = creds.get("refresh_token")
    if not refresh_token:
        logger.warning(
            "LinkedIn access token for agent %s has expired and no refresh token is stored. "
            "User must re-authenticate.",
            agent_id,
        )
        return creds

    try:
        token_data = await refresh_access_token(refresh_token)
    except Exception as exc:
        logger.warning("LinkedIn token refresh failed for agent %s: %s", agent_id, exc)
        return creds

    updated = {**creds, "access_token": token_data["access_token"]}
    if "refresh_token" in token_data:
        updated["refresh_token"] = token_data["refresh_token"]
    if "expires_in" in token_data:
        new_expires = now.timestamp() + float(token_data["expires_in"])
        updated["expires_at"] = datetime.fromtimestamp(new_expires, tz=timezone.utc).isoformat()

    SecretService.set_secret(db, agent_id, "linkedin", updated)
    logger.info("LinkedIn access token refreshed for agent %s", agent_id)
    return updated


async def _get_linkedin_client(db: Session, agent_id: str) -> tuple[httpx.AsyncClient, dict]:
    """Return an authenticated HTTP client and the (possibly refreshed) creds dict.

    The caller is responsible for using the client as an async context manager.
    Returning creds allows callers to read the person URN without a second
    SecretService lookup.
    """
    creds = SecretService.get_secret(db, agent_id, "linkedin")
    if not creds:
        raise Exception("LinkedIn credentials not found for agent")

    access_token = creds.get("access_token")
    if not access_token:
        raise Exception("LinkedIn access token not found in stored credentials")

    creds = await _maybe_refresh_creds(db, agent_id, creds)

    client = httpx.AsyncClient(
        base_url="https://api.linkedin.com/v2",
        headers={
            "Authorization": f"Bearer {creds['access_token']}",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )
    return client, creds


# ---------------------------------------------------------------------------
# API operations
# ---------------------------------------------------------------------------

@log_integration_call("linkedin", "GET", "/userinfo")
async def get_userinfo(db: Session, agent_id: str):
    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.get("/userinfo")
        resp.raise_for_status()
        return resp.json()


@log_integration_call("linkedin", "GET", "/me")
async def get_me(db: Session, agent_id: str):
    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.get("/me")
        resp.raise_for_status()
        return resp.json()


@log_integration_call("linkedin", "POST", "/ugcPosts")
async def create_ugc_post(db: Session, agent_id: str, author_urn: str, text: str):
    # Normalise so callers can pass either "abc123" or the full URN safely.
    author = _normalize_urn(author_urn, "person")

    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.post("/ugcPosts", json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        # Normalize the returned ID to ugcPost URN for consistency
        if "id" in data and data["id"].startswith("urn:li:share:"):
            data["ugcPostUrn"] = data["id"].replace("urn:li:share:", "urn:li:ugcPost:", 1)
        else:
            data["ugcPostUrn"] = data.get("id")
        
        return data


@log_integration_call("linkedin", "GET", "/ugcPosts/{ugcPostUrn}")
async def get_ugc_post(db: Session, agent_id: str, ugc_post_urn: str):
    urn = unquote(ugc_post_urn)
    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.get(f"/ugcPosts/{urn}")
        resp.raise_for_status()
        return resp.json()


@log_integration_call("linkedin", "DELETE", "/ugcPosts/{ugcPostUrn}")
async def delete_ugc_post(db: Session, agent_id: str, ugc_post_urn: str):
    urn = unquote(ugc_post_urn)
    
    # LinkedIn creates posts with urn:li:share: but the delete endpoint
    # requires urn:li:ugcPost: — convert if needed.
    if urn.startswith("urn:li:share:"):
        urn = urn.replace("urn:li:share:", "urn:li:ugcPost:", 1)
    
    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.delete(f"/ugcPosts/{urn}")
        resp.raise_for_status()
        return {"status": "success"} if resp.status_code == 204 else resp.json()


@log_integration_call("linkedin", "GET", "/connections")
async def get_connections(db: Session, agent_id: str):
    """Fetch first-degree connections.

    IMPORTANT: requires the r_network scope, which is a restricted LinkedIn
    permission. This call will return 403 unless your LinkedIn app has been
    explicitly approved for r_network. Check your app's granted scopes before
    calling this endpoint.
    """
    creds = SecretService.get_secret(db, agent_id, "linkedin")
    granted_scopes = (creds or {}).get("scope", "")
    if "r_network" not in granted_scopes.split():
        raise PermissionError(
            "get_connections requires the r_network scope, which has not been granted "
            "for this agent's LinkedIn credentials. The LinkedIn app must be approved "
            "for r_network and the user must re-authenticate with that scope."
        )

    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.get("/connections", params={"q": "viewer", "start": 0, "count": 50})
        resp.raise_for_status()
        return resp.json()


@log_integration_call("linkedin", "GET", "/organizationalEntityAcls")
async def get_organizations(db: Session, agent_id: str):
    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.get(
            "/organizationalEntityAcls",
            params={"q": "roleAssignee", "role": "ADMINISTRATOR"},
        )
        resp.raise_for_status()
        return resp.json()


@log_integration_call("linkedin", "POST", "/rest/images?action=initializeUpload")
async def initialize_image_upload(db: Session, agent_id: str, person_urn: str):
    """Register an image upload using the current LinkedIn Images API.

    Replaces the deprecated /v2/assets?action=registerUpload endpoint.
    Returns an upload URL and image URN to use in subsequent post creation.

    LinkedIn Images API docs:
    https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/images-api
    """
    owner = _normalize_urn(person_urn, "person")

    payload = {
        "initializeUploadRequest": {
            "owner": owner,
        }
    }

    # The Images API lives under /rest, not /v2
    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.post(
            "https://api.linkedin.com/rest/images?action=initializeUpload",
            json=payload,
            headers={"LinkedIn-Version": "202304"},  # pin to a stable monthly version
        )
        resp.raise_for_status()
        return resp.json()
        # Response shape: { "value": { "uploadUrl": "...", "image": "urn:li:image:..." } }


# ---------------------------------------------------------------------------
# Kept for backwards compatibility — will be removed in a future release.
# ---------------------------------------------------------------------------

@log_integration_call("linkedin", "POST", "/assets?action=registerUpload")
async def register_upload(
    db: Session,
    agent_id: str,
    person_urn: str,
    recipe: str = "urn:li:digitalmediaRecipe:feedshare-image",
):
    """DEPRECATED: use initialize_image_upload() instead.

    The /v2/assets registerUpload endpoint is being sunset by LinkedIn in
    favour of the Images API (/rest/images?action=initializeUpload).
    This function is kept temporarily for backwards compatibility.
    """
    import warnings
    warnings.warn(
        "register_upload() uses the deprecated LinkedIn Assets API. "
        "Switch to initialize_image_upload() which uses the current Images API.",
        DeprecationWarning,
        stacklevel=2,
    )

    owner = _normalize_urn(person_urn, "person")
    payload = {
        "registerUploadRequest": {
            "recipes": [recipe],
            "owner": owner,
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }
            ],
        }
    }

    client, _ = await _get_linkedin_client(db, agent_id)
    async with client:
        resp = await client.post("/assets?action=registerUpload", json=payload)
        resp.raise_for_status()
        return resp.json()