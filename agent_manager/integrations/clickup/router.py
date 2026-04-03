"""ClickUp endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    ClickUpAgentRequest,
    ClickUpTeamIdRequest,
    ClickUpSpaceIdRequest,
    ClickUpCreateSpaceRequest,
    ClickUpFolderIdRequest,
    ClickUpCreateFolderRequest,
    ClickUpListIdRequest,
    ClickUpCreateListRequest,
    ClickUpTaskIdRequest,
    ClickUpCreateTaskRequest,
    ClickUpUpdateTaskRequest,
    ClickUpCreateCommentRequest,
)

router = APIRouter()


@router.post("/teams/list", tags=["ClickUp"])
async def list_teams(body: ClickUpAgentRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_teams(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spaces/list", tags=["ClickUp"])
async def list_spaces(body: ClickUpTeamIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_spaces(db, body.agent_id, body.team_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spaces/{space_id}", tags=["ClickUp"])
async def get_space(agent_id: str, space_id: str, db: Session = Depends(get_db)):
    try:
        return await service.get_space(db, agent_id, space_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spaces/create", tags=["ClickUp"])
async def create_space(body: ClickUpCreateSpaceRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_space(db, body.agent_id, body.team_id, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folders/list", tags=["ClickUp"])
async def list_folders(body: ClickUpSpaceIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_folders(db, body.agent_id, body.space_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folders/{folder_id}", tags=["ClickUp"])
async def get_folder(agent_id: str, folder_id: str, db: Session = Depends(get_db)):
    try:
        return await service.get_folder(db, agent_id, folder_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folders/create", tags=["ClickUp"])
async def create_folder(body: ClickUpCreateFolderRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_folder(db, body.agent_id, body.space_id, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lists/list", tags=["ClickUp"])
async def list_lists(body: ClickUpFolderIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_lists(db, body.agent_id, body.folder_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lists/{list_id}", tags=["ClickUp"])
async def get_list(agent_id: str, list_id: str, db: Session = Depends(get_db)):
    try:
        return await service.get_list(db, agent_id, list_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lists/create", tags=["ClickUp"])
async def create_list(body: ClickUpCreateListRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_list(db, body.agent_id, body.folder_id, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/list", tags=["ClickUp"])
async def list_tasks(body: ClickUpListIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_tasks(db, body.agent_id, body.list_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", tags=["ClickUp"])
async def get_task(agent_id: str, task_id: str, db: Session = Depends(get_db)):
    try:
        return await service.get_task(db, agent_id, task_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/create", tags=["ClickUp"])
async def create_task(body: ClickUpCreateTaskRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_task(
            db, body.agent_id, body.list_id, body.name,
            description=body.description, assignees=body.assignees,
            priority=body.priority, due_date=body.due_date, status=body.status,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tasks/{task_id}", tags=["ClickUp"])
async def update_task(task_id: str, body: ClickUpUpdateTaskRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_task(
            db, body.agent_id, task_id,
            name=body.name, description=body.description,
            priority=body.priority, due_date=body.due_date, status=body.status,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}", tags=["ClickUp"])
async def delete_task(agent_id: str, task_id: str, db: Session = Depends(get_db)):
    try:
        return await service.delete_task(db, agent_id, task_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comments/list", tags=["ClickUp"])
async def list_comments(body: ClickUpTaskIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_comments(db, body.agent_id, body.task_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comments/create", tags=["ClickUp"])
async def create_comment(body: ClickUpCreateCommentRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_comment(db, body.agent_id, body.task_id, body.comment_text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
