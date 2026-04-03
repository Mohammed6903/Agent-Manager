"""Trello operations service.

With OAuth 2.0, the bearer token is injected automatically by the
OAuth2Handler — no manual API key/token injection needed.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "trello"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------

async def list_boards(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/members/me/boards")
        resp.raise_for_status()
        return resp.json()


async def get_board(db: Session, agent_id: str, board_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/boards/{board_id}")
        resp.raise_for_status()
        return resp.json()


async def create_board(db: Session, agent_id: str, name: str, desc: Optional[str] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {"name": name}
    if desc is not None:
        params["desc"] = desc
    async with client:
        resp = await client.post(f"{client.base_url}/boards", params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

async def get_board_lists(db: Session, agent_id: str, board_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/boards/{board_id}/lists")
        resp.raise_for_status()
        return resp.json()


async def create_list(db: Session, agent_id: str, name: str, id_board: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/lists", params={"name": name, "idBoard": id_board})
        resp.raise_for_status()
        return resp.json()


async def update_list(
    db: Session, agent_id: str, list_id: str,
    name: Optional[str] = None, closed: Optional[bool] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    if closed is not None:
        params["closed"] = str(closed).lower()
    async with client:
        resp = await client.put(f"{client.base_url}/lists/{list_id}", params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

async def get_list_cards(db: Session, agent_id: str, list_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/lists/{list_id}/cards")
        resp.raise_for_status()
        return resp.json()


async def get_card(db: Session, agent_id: str, card_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/cards/{card_id}")
        resp.raise_for_status()
        return resp.json()


async def create_card(
    db: Session, agent_id: str, id_list: str,
    name: Optional[str] = None, desc: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {"idList": id_list}
    if name is not None:
        params["name"] = name
    if desc is not None:
        params["desc"] = desc
    async with client:
        resp = await client.post(f"{client.base_url}/cards", params=params)
        resp.raise_for_status()
        return resp.json()


async def update_card(
    db: Session, agent_id: str, card_id: str,
    name: Optional[str] = None, desc: Optional[str] = None,
    id_list: Optional[str] = None, closed: Optional[bool] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    if desc is not None:
        params["desc"] = desc
    if id_list is not None:
        params["idList"] = id_list
    if closed is not None:
        params["closed"] = str(closed).lower()
    async with client:
        resp = await client.put(f"{client.base_url}/cards/{card_id}", params=params)
        resp.raise_for_status()
        return resp.json()


async def delete_card(db: Session, agent_id: str, card_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.delete(f"{client.base_url}/cards/{card_id}")
        resp.raise_for_status()
        if not resp.content:
            return {"status": "success"}
        return resp.json()


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

async def get_me(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/members/me")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

async def get_board_labels(db: Session, agent_id: str, board_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/boards/{board_id}/labels")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Checklists
# ---------------------------------------------------------------------------

async def create_checklist(db: Session, agent_id: str, id_card: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/checklists", params={"idCard": id_card, "name": name})
        resp.raise_for_status()
        return resp.json()


async def get_card_checklists(db: Session, agent_id: str, card_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/cards/{card_id}/checklists")
        resp.raise_for_status()
        return resp.json()
