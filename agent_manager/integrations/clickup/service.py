"""ClickUp operations service."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "clickup"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# Teams
async def list_teams(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/team")
        resp.raise_for_status()
        return resp.json()


# Spaces
async def list_spaces(db: Session, agent_id: str, team_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/team/{team_id}/space")
        resp.raise_for_status()
        return resp.json()


async def get_space(db: Session, agent_id: str, space_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/space/{space_id}")
        resp.raise_for_status()
        return resp.json()


async def create_space(db: Session, agent_id: str, team_id: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/team/{team_id}/space", json={"name": name})
        resp.raise_for_status()
        return resp.json()


# Folders
async def list_folders(db: Session, agent_id: str, space_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/space/{space_id}/folder")
        resp.raise_for_status()
        return resp.json()


async def get_folder(db: Session, agent_id: str, folder_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/folder/{folder_id}")
        resp.raise_for_status()
        return resp.json()


async def create_folder(db: Session, agent_id: str, space_id: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/space/{space_id}/folder", json={"name": name})
        resp.raise_for_status()
        return resp.json()


# Lists
async def list_lists(db: Session, agent_id: str, folder_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/folder/{folder_id}/list")
        resp.raise_for_status()
        return resp.json()


async def get_list(db: Session, agent_id: str, list_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/list/{list_id}")
        resp.raise_for_status()
        return resp.json()


async def create_list(db: Session, agent_id: str, folder_id: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/folder/{folder_id}/list", json={"name": name})
        resp.raise_for_status()
        return resp.json()


# Tasks
async def list_tasks(db: Session, agent_id: str, list_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/list/{list_id}/task")
        resp.raise_for_status()
        return resp.json()


async def get_task(db: Session, agent_id: str, task_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/task/{task_id}")
        resp.raise_for_status()
        return resp.json()


async def create_task(
    db: Session, agent_id: str, list_id: str, name: str,
    description: Optional[str] = None, assignees: Optional[List[int]] = None,
    priority: Optional[int] = None, due_date: Optional[int] = None,
    status: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"name": name}
    if description is not None:
        payload["description"] = description
    if assignees is not None:
        payload["assignees"] = assignees
    if priority is not None:
        payload["priority"] = priority
    if due_date is not None:
        payload["due_date"] = due_date
    if status is not None:
        payload["status"] = status
    async with client:
        resp = await client.post(f"{client.base_url}/list/{list_id}/task", json=payload)
        resp.raise_for_status()
        return resp.json()


async def update_task(
    db: Session, agent_id: str, task_id: str,
    name: Optional[str] = None, description: Optional[str] = None,
    priority: Optional[int] = None, due_date: Optional[int] = None,
    status: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if priority is not None:
        payload["priority"] = priority
    if due_date is not None:
        payload["due_date"] = due_date
    if status is not None:
        payload["status"] = status
    async with client:
        resp = await client.put(f"{client.base_url}/task/{task_id}", json=payload)
        resp.raise_for_status()
        return resp.json()


async def delete_task(db: Session, agent_id: str, task_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.delete(f"{client.base_url}/task/{task_id}")
        resp.raise_for_status()
        if not resp.content:
            return {"status": "success"}
        return resp.json()


# Comments
async def list_comments(db: Session, agent_id: str, task_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/task/{task_id}/comment")
        resp.raise_for_status()
        return resp.json()


async def create_comment(db: Session, agent_id: str, task_id: str, comment_text: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(
            f"{client.base_url}/task/{task_id}/comment",
            json={"comment_text": comment_text},
        )
        resp.raise_for_status()
        return resp.json()
