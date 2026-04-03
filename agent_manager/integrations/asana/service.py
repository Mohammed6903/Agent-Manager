"""Asana operations service."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "asana"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def get_me(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/users/me")
        resp.raise_for_status()
        return resp.json()


async def list_users(db: Session, agent_id: str, workspace: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/users", params={"workspace": workspace})
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

async def list_workspaces(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/workspaces")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

async def list_projects(
    db: Session, agent_id: str,
    workspace: Optional[str] = None, archived: Optional[bool] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if workspace is not None:
        params["workspace"] = workspace
    if archived is not None:
        params["archived"] = str(archived).lower()
    async with client:
        resp = await client.get(f"{client.base_url}/projects", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_project(db: Session, agent_id: str, project_gid: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/projects/{project_gid}")
        resp.raise_for_status()
        return resp.json()


async def create_project(
    db: Session, agent_id: str, workspace: str, name: str,
    notes: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    data: Dict[str, Any] = {"workspace": workspace, "name": name}
    if notes is not None:
        data["notes"] = notes
    async with client:
        resp = await client.post(f"{client.base_url}/projects", json={"data": data})
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

async def list_tasks(
    db: Session, agent_id: str, project_gid: str,
    completed_since: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if completed_since is not None:
        params["completed_since"] = completed_since
    async with client:
        resp = await client.get(f"{client.base_url}/projects/{project_gid}/tasks", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_task(db: Session, agent_id: str, task_gid: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/tasks/{task_gid}")
        resp.raise_for_status()
        return resp.json()


async def create_task(
    db: Session, agent_id: str,
    name: str, projects: Optional[List[str]] = None,
    workspace: Optional[str] = None, notes: Optional[str] = None,
    assignee: Optional[str] = None, due_on: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    data: Dict[str, Any] = {"name": name}
    if projects is not None:
        data["projects"] = projects
    if workspace is not None:
        data["workspace"] = workspace
    if notes is not None:
        data["notes"] = notes
    if assignee is not None:
        data["assignee"] = assignee
    if due_on is not None:
        data["due_on"] = due_on
    async with client:
        resp = await client.post(f"{client.base_url}/tasks", json={"data": data})
        resp.raise_for_status()
        return resp.json()


async def update_task(
    db: Session, agent_id: str, task_gid: str,
    name: Optional[str] = None, completed: Optional[bool] = None,
    notes: Optional[str] = None, assignee: Optional[str] = None,
    due_on: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    data: Dict[str, Any] = {}
    if name is not None:
        data["name"] = name
    if completed is not None:
        data["completed"] = completed
    if notes is not None:
        data["notes"] = notes
    if assignee is not None:
        data["assignee"] = assignee
    if due_on is not None:
        data["due_on"] = due_on
    async with client:
        resp = await client.put(f"{client.base_url}/tasks/{task_gid}", json={"data": data})
        resp.raise_for_status()
        return resp.json()


async def delete_task(db: Session, agent_id: str, task_gid: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.delete(f"{client.base_url}/tasks/{task_gid}")
        resp.raise_for_status()
        if resp.status_code == 200 and not resp.content:
            return {"status": "success"}
        return resp.json()


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

async def list_sections(db: Session, agent_id: str, project_gid: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/projects/{project_gid}/sections")
        resp.raise_for_status()
        return resp.json()


async def create_section(db: Session, agent_id: str, project_gid: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(
            f"{client.base_url}/projects/{project_gid}/sections",
            json={"data": {"name": name}},
        )
        resp.raise_for_status()
        return resp.json()
