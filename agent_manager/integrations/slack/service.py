"""Slack operations service."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "slack"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

async def list_channels(
    db: Session, agent_id: str,
    types: Optional[str] = None, limit: Optional[int] = None,
    cursor: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if types is not None:
        payload["types"] = types
    if limit is not None:
        payload["limit"] = limit
    if cursor is not None:
        payload["cursor"] = cursor
    async with client:
        resp = await client.post(f"{client.base_url}/conversations.list", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_channel_info(db: Session, agent_id: str, channel: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/conversations.info", json={"channel": channel})
        resp.raise_for_status()
        return resp.json()


async def create_channel(db: Session, agent_id: str, name: str, is_private: Optional[bool] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"name": name}
    if is_private is not None:
        payload["is_private"] = is_private
    async with client:
        resp = await client.post(f"{client.base_url}/conversations.create", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_channel_history(
    db: Session, agent_id: str, channel: str,
    limit: Optional[int] = None, oldest: Optional[str] = None,
    latest: Optional[str] = None, cursor: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"channel": channel}
    if limit is not None:
        payload["limit"] = limit
    if oldest is not None:
        payload["oldest"] = oldest
    if latest is not None:
        payload["latest"] = latest
    if cursor is not None:
        payload["cursor"] = cursor
    async with client:
        resp = await client.post(f"{client.base_url}/conversations.history", json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

async def post_message(
    db: Session, agent_id: str, channel: str, text: Optional[str] = None,
    blocks: Optional[List[Dict[str, Any]]] = None,
    thread_ts: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"channel": channel}
    if text is not None:
        payload["text"] = text
    if blocks is not None:
        payload["blocks"] = blocks
    if thread_ts is not None:
        payload["thread_ts"] = thread_ts
    async with client:
        resp = await client.post(f"{client.base_url}/chat.postMessage", json=payload)
        resp.raise_for_status()
        return resp.json()


async def update_message(
    db: Session, agent_id: str, channel: str, ts: str,
    text: Optional[str] = None, blocks: Optional[List[Dict[str, Any]]] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"channel": channel, "ts": ts}
    if text is not None:
        payload["text"] = text
    if blocks is not None:
        payload["blocks"] = blocks
    async with client:
        resp = await client.post(f"{client.base_url}/chat.update", json=payload)
        resp.raise_for_status()
        return resp.json()


async def delete_message(db: Session, agent_id: str, channel: str, ts: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/chat.delete", json={"channel": channel, "ts": ts})
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def list_users(db: Session, agent_id: str, limit: Optional[int] = None, cursor: Optional[str] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if limit is not None:
        payload["limit"] = limit
    if cursor is not None:
        payload["cursor"] = cursor
    async with client:
        resp = await client.post(f"{client.base_url}/users.list", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_user_info(db: Session, agent_id: str, user: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/users.info", json={"user": user})
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

async def add_reaction(db: Session, agent_id: str, channel: str, timestamp: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(
            f"{client.base_url}/reactions.add",
            json={"channel": channel, "timestamp": timestamp, "name": name},
        )
        resp.raise_for_status()
        return resp.json()


async def remove_reaction(db: Session, agent_id: str, channel: str, timestamp: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(
            f"{client.base_url}/reactions.remove",
            json={"channel": channel, "timestamp": timestamp, "name": name},
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

async def list_files(
    db: Session, agent_id: str,
    channel: Optional[str] = None, count: Optional[int] = None,
    page: Optional[int] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if channel is not None:
        payload["channel"] = channel
    if count is not None:
        payload["count"] = count
    if page is not None:
        payload["page"] = page
    async with client:
        resp = await client.post(f"{client.base_url}/files.list", json=payload)
        resp.raise_for_status()
        return resp.json()
