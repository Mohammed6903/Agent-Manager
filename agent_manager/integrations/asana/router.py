"""Asana endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    AsanaAgentRequest,
    AsanaWorkspaceUsersRequest,
    AsanaListProjectsRequest,
    AsanaProjectRequest,
    AsanaCreateProjectRequest,
    AsanaListTasksRequest,
    AsanaTaskRequest,
    AsanaCreateTaskRequest,
    AsanaUpdateTaskRequest,
    AsanaCreateSectionRequest,
)

router = APIRouter()


@router.get("/users/me", tags=["Asana"])
async def get_me(agent_id: str, db: Session = Depends(get_db)):
    """Get the authenticated user."""
    try:
        return await service.get_me(db, agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/list", tags=["Asana"])
async def list_users(body: AsanaWorkspaceUsersRequest, db: Session = Depends(get_db)):
    """List users in a workspace."""
    try:
        return await service.list_users(db, body.agent_id, body.workspace)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/list", tags=["Asana"])
async def list_workspaces(body: AsanaAgentRequest, db: Session = Depends(get_db)):
    """List workspaces."""
    try:
        return await service.list_workspaces(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/list", tags=["Asana"])
async def list_projects(body: AsanaListProjectsRequest, db: Session = Depends(get_db)):
    """List projects."""
    try:
        return await service.list_projects(db, body.agent_id, workspace=body.workspace, archived=body.archived)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_gid}", tags=["Asana"])
async def get_project(agent_id: str, project_gid: str, db: Session = Depends(get_db)):
    """Get a project."""
    try:
        return await service.get_project(db, agent_id, project_gid)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/create", tags=["Asana"])
async def create_project(body: AsanaCreateProjectRequest, db: Session = Depends(get_db)):
    """Create a project."""
    try:
        return await service.create_project(db, body.agent_id, body.workspace, body.name, notes=body.notes)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/list", tags=["Asana"])
async def list_tasks(body: AsanaListTasksRequest, db: Session = Depends(get_db)):
    """List tasks in a project."""
    try:
        return await service.list_tasks(db, body.agent_id, body.project_gid, completed_since=body.completed_since)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_gid}", tags=["Asana"])
async def get_task(agent_id: str, task_gid: str, db: Session = Depends(get_db)):
    """Get a task."""
    try:
        return await service.get_task(db, agent_id, task_gid)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/create", tags=["Asana"])
async def create_task(body: AsanaCreateTaskRequest, db: Session = Depends(get_db)):
    """Create a task."""
    try:
        return await service.create_task(
            db, body.agent_id, body.name,
            projects=body.projects, workspace=body.workspace,
            notes=body.notes, assignee=body.assignee, due_on=body.due_on,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tasks/{task_gid}", tags=["Asana"])
async def update_task(task_gid: str, body: AsanaUpdateTaskRequest, db: Session = Depends(get_db)):
    """Update a task."""
    try:
        return await service.update_task(
            db, body.agent_id, task_gid,
            name=body.name, completed=body.completed,
            notes=body.notes, assignee=body.assignee, due_on=body.due_on,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_gid}", tags=["Asana"])
async def delete_task(agent_id: str, task_gid: str, db: Session = Depends(get_db)):
    """Delete a task."""
    try:
        return await service.delete_task(db, agent_id, task_gid)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sections/list", tags=["Asana"])
async def list_sections(body: AsanaProjectRequest, db: Session = Depends(get_db)):
    """List sections in a project."""
    try:
        return await service.list_sections(db, body.agent_id, body.project_gid)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sections/create", tags=["Asana"])
async def create_section(body: AsanaCreateSectionRequest, db: Session = Depends(get_db)):
    """Create a section in a project."""
    try:
        return await service.create_section(db, body.agent_id, body.project_gid, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
