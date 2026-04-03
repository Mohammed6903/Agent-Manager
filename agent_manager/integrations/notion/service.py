"""Notion operations service.

Uses IntegrationService.get_client() to obtain an IntegrationClient that handles
auth injection (bearer token + Notion-Version header) and request logging
automatically.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService
from ...dependencies import get_agent_service

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "notion"


async def _get_client(db: Session, agent_id: str):
    """Build an IntegrationClient for the given agent's Notion integration."""
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search(
    db: Session,
    agent_id: str,
    query: Optional[str] = None,
    filter: Optional[Dict[str, Any]] = None,
    sort: Optional[Dict[str, Any]] = None,
    start_cursor: Optional[str] = None,
    page_size: Optional[int] = None,
):
    """POST /search — Search pages and databases in workspace."""
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if query is not None:
        payload["query"] = query
    if filter is not None:
        payload["filter"] = filter
    if sort is not None:
        payload["sort"] = sort
    if start_cursor is not None:
        payload["start_cursor"] = start_cursor
    if page_size is not None:
        payload["page_size"] = page_size

    async with client:
        resp = await client.post(f"{client.base_url}/search", json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

async def create_page(
    db: Session,
    agent_id: str,
    parent: Dict[str, Any],
    properties: Dict[str, Any],
    children: Optional[List[Dict[str, Any]]] = None,
    icon: Optional[Dict[str, Any]] = None,
    cover: Optional[Dict[str, Any]] = None,
):
    """POST /pages — Create a new page."""
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"parent": parent, "properties": properties}
    if children is not None:
        payload["children"] = children
    if icon is not None:
        payload["icon"] = icon
    if cover is not None:
        payload["cover"] = cover

    async with client:
        resp = await client.post(f"{client.base_url}/pages", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_page(db: Session, agent_id: str, page_id: str):
    """GET /pages/{page_id} — Retrieve a page."""
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/pages/{page_id}")
        resp.raise_for_status()
        return resp.json()


async def update_page(
    db: Session,
    agent_id: str,
    page_id: str,
    properties: Optional[Dict[str, Any]] = None,
    archived: Optional[bool] = None,
    icon: Optional[Dict[str, Any]] = None,
    cover: Optional[Dict[str, Any]] = None,
):
    """PATCH /pages/{page_id} — Update page properties."""
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if properties is not None:
        payload["properties"] = properties
    if archived is not None:
        payload["archived"] = archived
    if icon is not None:
        payload["icon"] = icon
    if cover is not None:
        payload["cover"] = cover

    async with client:
        resp = await client.patch(f"{client.base_url}/pages/{page_id}", json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Blocks (page content)
# ---------------------------------------------------------------------------

async def get_block_children(
    db: Session,
    agent_id: str,
    block_id: str,
    start_cursor: Optional[str] = None,
    page_size: Optional[int] = None,
):
    """GET /blocks/{block_id}/children — Read page content."""
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if start_cursor is not None:
        params["start_cursor"] = start_cursor
    if page_size is not None:
        params["page_size"] = page_size

    async with client:
        resp = await client.get(
            f"{client.base_url}/blocks/{block_id}/children", params=params
        )
        resp.raise_for_status()
        return resp.json()


async def append_block_children(
    db: Session,
    agent_id: str,
    block_id: str,
    children: List[Dict[str, Any]],
    after: Optional[str] = None,
):
    """PATCH /blocks/{block_id}/children — Append block children."""
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"children": children}
    if after is not None:
        payload["after"] = after

    async with client:
        resp = await client.patch(
            f"{client.base_url}/blocks/{block_id}/children", json=payload
        )
        resp.raise_for_status()
        return resp.json()


async def update_block(
    db: Session, agent_id: str, block_id: str, block_data: Dict[str, Any]
):
    """PATCH /blocks/{block_id} — Update a block."""
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.patch(
            f"{client.base_url}/blocks/{block_id}", json=block_data
        )
        resp.raise_for_status()
        return resp.json()


async def delete_block(db: Session, agent_id: str, block_id: str):
    """DELETE /blocks/{block_id} — Delete (archive) a block."""
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.delete(f"{client.base_url}/blocks/{block_id}")
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {"status": "success"}
        return resp.json()


# ---------------------------------------------------------------------------
# Databases
# ---------------------------------------------------------------------------

async def create_database(
    db: Session,
    agent_id: str,
    parent: Dict[str, Any],
    title: List[Dict[str, Any]],
    properties: Dict[str, Any],
):
    """POST /databases — Create a database."""
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {
        "parent": parent,
        "title": title,
        "properties": properties,
    }
    async with client:
        resp = await client.post(f"{client.base_url}/databases", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_database(db: Session, agent_id: str, database_id: str):
    """GET /databases/{database_id} — Retrieve a database."""
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/databases/{database_id}")
        resp.raise_for_status()
        return resp.json()


async def query_database(
    db: Session,
    agent_id: str,
    database_id: str,
    filter: Optional[Dict[str, Any]] = None,
    sorts: Optional[List[Dict[str, Any]]] = None,
    start_cursor: Optional[str] = None,
    page_size: Optional[int] = None,
):
    """POST /databases/{database_id}/query — Query a database."""
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if filter is not None:
        payload["filter"] = filter
    if sorts is not None:
        payload["sorts"] = sorts
    if start_cursor is not None:
        payload["start_cursor"] = start_cursor
    if page_size is not None:
        payload["page_size"] = page_size

    async with client:
        resp = await client.post(
            f"{client.base_url}/databases/{database_id}/query", json=payload
        )
        resp.raise_for_status()
        return resp.json()


async def update_database(
    db: Session,
    agent_id: str,
    database_id: str,
    title: Optional[List[Dict[str, Any]]] = None,
    properties: Optional[Dict[str, Any]] = None,
):
    """PATCH /databases/{database_id} — Update a database."""
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if properties is not None:
        payload["properties"] = properties

    async with client:
        resp = await client.patch(
            f"{client.base_url}/databases/{database_id}", json=payload
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def list_users(db: Session, agent_id: str):
    """GET /users — List all users in workspace."""
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/users")
        resp.raise_for_status()
        return resp.json()


async def get_user(db: Session, agent_id: str, user_id: str):
    """GET /users/{user_id} — Retrieve a user."""
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/users/{user_id}")
        resp.raise_for_status()
        return resp.json()


async def get_bot_user(db: Session, agent_id: str):
    """GET /users/me — Get the bot user."""
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/users/me")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

async def create_comment(
    db: Session,
    agent_id: str,
    rich_text: List[Dict[str, Any]],
    parent: Optional[Dict[str, Any]] = None,
    discussion_id: Optional[str] = None,
):
    """POST /comments — Create a comment on a page or discussion."""
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"rich_text": rich_text}
    if parent is not None:
        payload["parent"] = parent
    if discussion_id is not None:
        payload["discussion_id"] = discussion_id

    async with client:
        resp = await client.post(f"{client.base_url}/comments", json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_comments(
    db: Session,
    agent_id: str,
    block_id: str,
    start_cursor: Optional[str] = None,
    page_size: Optional[int] = None,
):
    """GET /comments — Retrieve comments for a block or page."""
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {"block_id": block_id}
    if start_cursor is not None:
        params["start_cursor"] = start_cursor
    if page_size is not None:
        params["page_size"] = page_size

    async with client:
        resp = await client.get(f"{client.base_url}/comments", params=params)
        resp.raise_for_status()
        return resp.json()
