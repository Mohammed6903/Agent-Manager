"""Garage Feed router — endpoints for creating posts on the Garage community feed."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..services.secret_service import SecretService

logger = logging.getLogger("agent_manager.routers.garage_router")

router = APIRouter()


# ── Request schemas ─────────────────────────────────────────────────────────────

class CreateGaragePostRequest(BaseModel):
    agent_id: str
    content: str


# ── Endpoints ───────────────────────────────────────────────────────────────────

@router.post("/posts", tags=["Garage Feed"], status_code=201)
async def create_garage_post(
    body: CreateGaragePostRequest,
    db: Session = Depends(get_db),
):
    """Create a post on the Garage community feed.

    Fetches the agent's `garage_feed` credentials from the secret store
    and forwards the post to the Garage API.
    """
    creds = SecretService.get_secret(db, body.agent_id, "garage")
    if not creds:
        raise HTTPException(
            status_code=404,
            detail="Garage Feed skill is not connected for this agent.",
        )

    token = creds.get("token", "")
    org_id = creds.get("orgId", "")
    channel_ids = creds.get("channelIds", [])

    # channelIds may come back as a string from decryption — parse if needed
    if isinstance(channel_ids, str):
        import json as _json
        try:
            channel_ids = _json.loads(channel_ids)
        except (ValueError, TypeError):
            channel_ids = [channel_ids] if channel_ids else []

    if not token or not org_id:
        raise HTTPException(
            status_code=422,
            detail="Garage Feed credentials are incomplete (missing token or orgId). Please reconnect the skill.",
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.GARAGE_API_URL}/feed/posts",
                params={"orgId": org_id},
                json={"content": body.content, "channelIds": channel_ids},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code in (200, 201):
                return {
                    "status": "published",
                    "message": "Post published successfully on the Garage feed!",
                }
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Garage API error: {resp.text[:300]}",
            )
    except httpx.HTTPError as exc:
        logger.error("Garage post error for agent %s: %s", body.agent_id, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Error connecting to Garage API: {exc}",
        )
