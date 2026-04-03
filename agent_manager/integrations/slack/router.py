"""Slack endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    SlackListChannelsRequest,
    SlackChannelRequest,
    SlackCreateChannelRequest,
    SlackChannelHistoryRequest,
    SlackPostMessageRequest,
    SlackUpdateMessageRequest,
    SlackDeleteMessageRequest,
    SlackReactionRequest,
    SlackListFilesRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

@router.post("/conversations/list", tags=["Slack"])
async def list_channels(body: SlackListChannelsRequest, db: Session = Depends(get_db)):
    """List channels in the workspace."""
    try:
        return await service.list_channels(
            db, body.agent_id, types=body.types, limit=body.limit, cursor=body.cursor,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/info", tags=["Slack"])
async def get_channel_info(body: SlackChannelRequest, db: Session = Depends(get_db)):
    """Get info about a channel."""
    try:
        return await service.get_channel_info(db, body.agent_id, body.channel)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/create", tags=["Slack"])
async def create_channel(body: SlackCreateChannelRequest, db: Session = Depends(get_db)):
    """Create a new channel."""
    try:
        return await service.create_channel(db, body.agent_id, body.name, is_private=body.is_private)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/history", tags=["Slack"])
async def get_channel_history(body: SlackChannelHistoryRequest, db: Session = Depends(get_db)):
    """Get message history of a channel."""
    try:
        return await service.get_channel_history(
            db, body.agent_id, body.channel,
            limit=body.limit, oldest=body.oldest, latest=body.latest, cursor=body.cursor,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.post("/chat/postMessage", tags=["Slack"])
async def post_message(body: SlackPostMessageRequest, db: Session = Depends(get_db)):
    """Send a message to a channel."""
    try:
        return await service.post_message(
            db, body.agent_id, body.channel,
            text=body.text, blocks=body.blocks, thread_ts=body.thread_ts,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/update", tags=["Slack"])
async def update_message(body: SlackUpdateMessageRequest, db: Session = Depends(get_db)):
    """Update an existing message."""
    try:
        return await service.update_message(
            db, body.agent_id, body.channel, body.ts,
            text=body.text, blocks=body.blocks,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/delete", tags=["Slack"])
async def delete_message(body: SlackDeleteMessageRequest, db: Session = Depends(get_db)):
    """Delete a message."""
    try:
        return await service.delete_message(db, body.agent_id, body.channel, body.ts)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.post("/users/list", tags=["Slack"])
async def list_users(body: SlackListChannelsRequest, db: Session = Depends(get_db)):
    """List all users in workspace."""
    try:
        return await service.list_users(db, body.agent_id, limit=body.limit, cursor=body.cursor)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/info", tags=["Slack"])
async def get_user_info(body: SlackChannelRequest, db: Session = Depends(get_db)):
    """Get info about a user."""
    try:
        return await service.get_user_info(db, body.agent_id, body.channel)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

@router.post("/reactions/add", tags=["Slack"])
async def add_reaction(body: SlackReactionRequest, db: Session = Depends(get_db)):
    """Add a reaction to a message."""
    try:
        return await service.add_reaction(db, body.agent_id, body.channel, body.timestamp, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reactions/remove", tags=["Slack"])
async def remove_reaction(body: SlackReactionRequest, db: Session = Depends(get_db)):
    """Remove a reaction from a message."""
    try:
        return await service.remove_reaction(db, body.agent_id, body.channel, body.timestamp, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

@router.post("/files/list", tags=["Slack"])
async def list_files(body: SlackListFilesRequest, db: Session = Depends(get_db)):
    """List files shared in the workspace."""
    try:
        return await service.list_files(
            db, body.agent_id, channel=body.channel, count=body.count, page=body.page,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
