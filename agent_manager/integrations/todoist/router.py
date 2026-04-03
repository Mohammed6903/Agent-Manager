"""Todoist endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    TodoistAgentRequest,
    TodoistProjectIdRequest,
    TodoistCreateProjectRequest,
    TodoistUpdateProjectRequest,
    TodoistListTasksRequest,
    TodoistTaskIdRequest,
    TodoistCreateTaskRequest,
    TodoistUpdateTaskRequest,
    TodoistListCommentsRequest,
    TodoistCreateCommentRequest,
    TodoistCreateLabelRequest,
    TodoistCreateSectionRequest,
)

router = APIRouter()


# Projects
@router.post("/projects/list", tags=["Todoist"])
async def list_projects(body: TodoistAgentRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_projects(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/get", tags=["Todoist"])
async def get_project(body: TodoistProjectIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_project(db, body.agent_id, body.project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/create", tags=["Todoist"])
async def create_project(body: TodoistCreateProjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_project(db, body.agent_id, body.name, parent_id=body.parent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/update/{project_id}", tags=["Todoist"])
async def update_project(project_id: str, body: TodoistUpdateProjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_project(db, body.agent_id, project_id, name=body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}", tags=["Todoist"])
async def delete_project(agent_id: str, project_id: str, db: Session = Depends(get_db)):
    try:
        return await service.delete_project(db, agent_id, project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Tasks
@router.post("/tasks/list", tags=["Todoist"])
async def list_tasks(body: TodoistListTasksRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_tasks(db, body.agent_id, project_id=body.project_id, label=body.label)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/get", tags=["Todoist"])
async def get_task(body: TodoistTaskIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_task(db, body.agent_id, body.task_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/create", tags=["Todoist"])
async def create_task(body: TodoistCreateTaskRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_task(
            db, body.agent_id, body.content,
            project_id=body.project_id, description=body.description,
            due_string=body.due_string, priority=body.priority, labels=body.labels,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/update/{task_id}", tags=["Todoist"])
async def update_task(task_id: str, body: TodoistUpdateTaskRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_task(
            db, body.agent_id, task_id,
            content=body.content, description=body.description,
            due_string=body.due_string, priority=body.priority,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/close", tags=["Todoist"])
async def close_task(agent_id: str, task_id: str, db: Session = Depends(get_db)):
    try:
        return await service.close_task(db, agent_id, task_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/reopen", tags=["Todoist"])
async def reopen_task(agent_id: str, task_id: str, db: Session = Depends(get_db)):
    try:
        return await service.reopen_task(db, agent_id, task_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}", tags=["Todoist"])
async def delete_task(agent_id: str, task_id: str, db: Session = Depends(get_db)):
    try:
        return await service.delete_task(db, agent_id, task_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Comments
@router.post("/comments/list", tags=["Todoist"])
async def list_comments(body: TodoistListCommentsRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_comments(db, body.agent_id, task_id=body.task_id, project_id=body.project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comments/create", tags=["Todoist"])
async def create_comment(body: TodoistCreateCommentRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_comment(db, body.agent_id, body.content, task_id=body.task_id, project_id=body.project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Labels
@router.post("/labels/list", tags=["Todoist"])
async def list_labels(body: TodoistAgentRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_labels(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/labels/create", tags=["Todoist"])
async def create_label(body: TodoistCreateLabelRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_label(db, body.agent_id, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Sections
@router.post("/sections/list", tags=["Todoist"])
async def list_sections(body: TodoistProjectIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_sections(db, body.agent_id, body.project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sections/create", tags=["Todoist"])
async def create_section(body: TodoistCreateSectionRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_section(db, body.agent_id, body.project_id, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
