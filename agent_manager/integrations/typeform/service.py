"""Typeform operations service."""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "typeform"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# Forms
async def list_forms(db: Session, agent_id: str, page: Optional[int] = None, page_size: Optional[int] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["page_size"] = page_size
    async with client:
        resp = await client.get(f"{client.base_url}/forms", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_form(db: Session, agent_id: str, form_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/forms/{form_id}")
        resp.raise_for_status()
        return resp.json()


async def create_form(db: Session, agent_id: str, form_data: Dict[str, Any]):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/forms", json=form_data)
        resp.raise_for_status()
        return resp.json()


async def update_form(db: Session, agent_id: str, form_id: str, form_data: Dict[str, Any]):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.put(f"{client.base_url}/forms/{form_id}", json=form_data)
        resp.raise_for_status()
        return resp.json()


async def delete_form(db: Session, agent_id: str, form_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.delete(f"{client.base_url}/forms/{form_id}")
        resp.raise_for_status()
        return {"status": "success"}


# Responses
async def list_responses(
    db: Session, agent_id: str, form_id: str,
    page_size: Optional[int] = None, since: Optional[str] = None,
    until: Optional[str] = None, after: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if page_size is not None:
        params["page_size"] = page_size
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    if after is not None:
        params["after"] = after
    async with client:
        resp = await client.get(f"{client.base_url}/forms/{form_id}/responses", params=params)
        resp.raise_for_status()
        return resp.json()


# Workspaces
async def list_workspaces(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/workspaces")
        resp.raise_for_status()
        return resp.json()


async def get_workspace(db: Session, agent_id: str, workspace_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/workspaces/{workspace_id}")
        resp.raise_for_status()
        return resp.json()
