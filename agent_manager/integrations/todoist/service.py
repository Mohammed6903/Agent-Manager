"""Todoist operations service."""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "todoist"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# Projects
async def list_projects(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/projects")
        resp.raise_for_status()
        return resp.json()


async def get_project(db: Session, agent_id: str, project_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/projects/{project_id}")
        resp.raise_for_status()
        return resp.json()


async def create_project(db: Session, agent_id: str, name: str, parent_id: Optional[str] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    async with client:
        resp = await client.post(f"{client.base_url}/projects", json=payload)
        resp.raise_for_status()
        return resp.json()


async def update_project(db: Session, agent_id: str, project_id: str, name: Optional[str] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    async with client:
        resp = await client.post(f"{client.base_url}/projects/{project_id}", json=payload)
        resp.raise_for_status()
        return resp.json()


async def delete_project(db: Session, agent_id: str, project_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.delete(f"{client.base_url}/projects/{project_id}")
        resp.raise_for_status()
        return {"status": "success"}


# Tasks
async def list_tasks(
    db: Session, agent_id: str,
    project_id: Optional[str] = None, label: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if project_id is not None:
        params["project_id"] = project_id
    if label is not None:
        params["label"] = label
    async with client:
        resp = await client.get(f"{client.base_url}/tasks", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_task(db: Session, agent_id: str, task_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/tasks/{task_id}")
        resp.raise_for_status()
        return resp.json()


async def create_task(
    db: Session, agent_id: str, content: str,
    project_id: Optional[str] = None, description: Optional[str] = None,
    due_string: Optional[str] = None, priority: Optional[int] = None,
    labels: Optional[list] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"content": content}
    if project_id is not None:
        payload["project_id"] = project_id
    if description is not None:
        payload["description"] = description
    if due_string is not None:
        payload["due_string"] = due_string
    if priority is not None:
        payload["priority"] = priority
    if labels is not None:
        payload["labels"] = labels
    async with client:
        resp = await client.post(f"{client.base_url}/tasks", json=payload)
        resp.raise_for_status()
        return resp.json()


async def update_task(
    db: Session, agent_id: str, task_id: str,
    content: Optional[str] = None, description: Optional[str] = None,
    due_string: Optional[str] = None, priority: Optional[int] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if content is not None:
        payload["content"] = content
    if description is not None:
        payload["description"] = description
    if due_string is not None:
        payload["due_string"] = due_string
    if priority is not None:
        payload["priority"] = priority
    async with client:
        resp = await client.post(f"{client.base_url}/tasks/{task_id}", json=payload)
        resp.raise_for_status()
        return resp.json()


async def close_task(db: Session, agent_id: str, task_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/tasks/{task_id}/close")
        resp.raise_for_status()
        return {"status": "success"}


async def reopen_task(db: Session, agent_id: str, task_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/tasks/{task_id}/reopen")
        resp.raise_for_status()
        return {"status": "success"}


async def delete_task(db: Session, agent_id: str, task_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.delete(f"{client.base_url}/tasks/{task_id}")
        resp.raise_for_status()
        return {"status": "success"}


# Comments
async def list_comments(db: Session, agent_id: str, task_id: Optional[str] = None, project_id: Optional[str] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if task_id is not None:
        params["task_id"] = task_id
    if project_id is not None:
        params["project_id"] = project_id
    async with client:
        resp = await client.get(f"{client.base_url}/comments", params=params)
        resp.raise_for_status()
        return resp.json()


async def create_comment(
    db: Session, agent_id: str, content: str,
    task_id: Optional[str] = None, project_id: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"content": content}
    if task_id is not None:
        payload["task_id"] = task_id
    if project_id is not None:
        payload["project_id"] = project_id
    async with client:
        resp = await client.post(f"{client.base_url}/comments", json=payload)
        resp.raise_for_status()
        return resp.json()


# Labels
async def list_labels(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/labels")
        resp.raise_for_status()
        return resp.json()


async def create_label(db: Session, agent_id: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/labels", json={"name": name})
        resp.raise_for_status()
        return resp.json()


# Sections
async def list_sections(db: Session, agent_id: str, project_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/sections", params={"project_id": project_id})
        resp.raise_for_status()
        return resp.json()


async def create_section(db: Session, agent_id: str, project_id: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/sections", json={"project_id": project_id, "name": name})
        resp.raise_for_status()
        return resp.json()
