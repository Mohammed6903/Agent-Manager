"""Garage Feed router — endpoints for creating posts on the Garage community feed."""

from __future__ import annotations

import ast
import json
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
    creds = SecretService.get_secret(db, body.agent_id, "garage_feed")
    if not creds:
        raise HTTPException(
            status_code=404,
            detail="Garage Feed skill is not connected for this agent.",
        )

    token = creds.get("token", "")
    org_id = creds.get("orgId", "")
    channel_ids = creds.get("channelIds", [])

    # channelIds is decrypted as a string (because encrypt does str(v)).
    # It might be in various formats:
    # - "['id1', 'id2']" (Python repr, from our old str(list))
    # - "[\"id1\", \"id2\"]" (Valid JSON)
    # - "id1, id2" (Comma-separated)
    # - "id1" (Single string)
    if isinstance(channel_ids, str):
        channel_ids = channel_ids.strip()
        if channel_ids.startswith("[") and channel_ids.endswith("]"):
            try:
                channel_ids = json.loads(channel_ids)
            except (ValueError, TypeError):
                try:
                    channel_ids = ast.literal_eval(channel_ids)
                except (ValueError, SyntaxError):
                    channel_ids = []
        elif "," in channel_ids:
            channel_ids = [c.strip() for c in channel_ids.split(",") if c.strip()]
        elif channel_ids:
            channel_ids = [channel_ids]
        else:
            channel_ids = []

    if not token or not org_id:
        raise HTTPException(
            status_code=422,
            detail="Garage Feed credentials are incomplete (missing token or orgId). Please reconnect the skill.",
        )

    # Debug: log what we're sending (mask the token for security)
    masked_token = f"{token[:8]}...{token[-4:]}" if len(token) > 12 else "***"
    logger.info(
        "Garage post request — orgId=%s, token=%s (len=%d), channelIds=%s",
        org_id, masked_token, len(token), channel_ids,
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
            logger.error(
                "Garage API returned %d: %s", resp.status_code, resp.text[:500],
            )
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
