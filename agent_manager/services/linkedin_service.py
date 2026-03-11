"""LinkedIn operations service."""

import logging
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
import httpx

from .secret_service import SecretService
from ..integrations.sdk_logger import log_integration_call

logger = logging.getLogger(__name__)

def _get_linkedin_client(db: Session, agent_id: str) -> httpx.AsyncClient:
    """Helper to get an authenticated HTTP client for LinkedIn API v2."""
    creds = SecretService.get_secret(db, agent_id, "linkedin")
    if not creds:
        raise Exception("LinkedIn credentials not found for agent")
    
    access_token = creds.get("access_token")
    if not access_token:
        raise Exception("LinkedIn access token not found in stored credentials")
        
    return httpx.AsyncClient(
        base_url="https://api.linkedin.com/v2",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }
    )

@log_integration_call("linkedin", "GET", "/userinfo")
async def get_userinfo(db: Session, agent_id: str):
    async with _get_linkedin_client(db, agent_id) as client:
        resp = await client.get("/userinfo")
        resp.raise_for_status()
        return resp.json()

@log_integration_call("linkedin", "GET", "/me")
async def get_me(db: Session, agent_id: str):
    async with _get_linkedin_client(db, agent_id) as client:
        resp = await client.get("/me")
        resp.raise_for_status()
        return resp.json()

@log_integration_call("linkedin", "POST", "/ugcPosts")
async def create_ugc_post(db: Session, agent_id: str, author_urn: str, text: str):
    payload = {
        "author": f"urn:li:person:{author_urn}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }
    
    async with _get_linkedin_client(db, agent_id) as client:
        resp = await client.post("/ugcPosts", json=payload)
        resp.raise_for_status()
        return resp.json()

@log_integration_call("linkedin", "GET", "/ugcPosts/{ugcPostUrn}")
async def get_ugc_post(db: Session, agent_id: str, ugc_post_urn: str):
    async with _get_linkedin_client(db, agent_id) as client:
        resp = await client.get(f"/ugcPosts/{ugc_post_urn}")
        resp.raise_for_status()
        return resp.json()

@log_integration_call("linkedin", "DELETE", "/ugcPosts/{ugcPostUrn}")
async def delete_ugc_post(db: Session, agent_id: str, ugc_post_urn: str):
    async with _get_linkedin_client(db, agent_id) as client:
        resp = await client.delete(f"/ugcPosts/{ugc_post_urn}")
        resp.raise_for_status()
        return {"status": "success"} if resp.status_code == 204 else resp.json()

@log_integration_call("linkedin", "GET", "/connections")
async def get_connections(db: Session, agent_id: str):
    async with _get_linkedin_client(db, agent_id) as client:
        # Note: Depending on permissions this might require r_network scope
        resp = await client.get("/connections", params={"q": "viewer", "start": 0, "count": 50})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("linkedin", "GET", "/organizationalEntityAcls")
async def get_organizations(db: Session, agent_id: str):
    async with _get_linkedin_client(db, agent_id) as client:
        resp = await client.get("/organizationalEntityAcls", params={"q": "roleAssignee", "role": "ADMINISTRATOR"})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("linkedin", "POST", "/assets?action=registerUpload")
async def register_upload(db: Session, agent_id: str, person_urn: str, recipe: str = "urn:li:digitalmediaRecipe:feedshare-image"):
    payload = {
        "registerUploadRequest": {
            "recipes": [recipe],
            "owner": f"urn:li:person:{person_urn}",
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent"
                }
            ]
        }
    }
    async with _get_linkedin_client(db, agent_id) as client:
        resp = await client.post("/assets?action=registerUpload", json=payload)
        resp.raise_for_status()
        return resp.json()
