"""Typeform endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    TypeformAgentRequest,
    TypeformListFormsRequest,
    TypeformFormIdRequest,
    TypeformCreateFormRequest,
    TypeformUpdateFormRequest,
    TypeformListResponsesRequest,
    TypeformWorkspaceIdRequest,
)

router = APIRouter()


@router.post("/forms/list", tags=["Typeform"])
async def list_forms(body: TypeformListFormsRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_forms(db, body.agent_id, page=body.page, page_size=body.page_size)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/forms/get", tags=["Typeform"])
async def get_form(body: TypeformFormIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_form(db, body.agent_id, body.form_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/forms/create", tags=["Typeform"])
async def create_form(body: TypeformCreateFormRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_form(db, body.agent_id, body.form_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/forms/update/{form_id}", tags=["Typeform"])
async def update_form(form_id: str, body: TypeformUpdateFormRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_form(db, body.agent_id, form_id, body.form_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/forms/{form_id}", tags=["Typeform"])
async def delete_form(agent_id: str, form_id: str, db: Session = Depends(get_db)):
    try:
        return await service.delete_form(db, agent_id, form_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/responses/list", tags=["Typeform"])
async def list_responses(body: TypeformListResponsesRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_responses(
            db, body.agent_id, body.form_id,
            page_size=body.page_size, since=body.since, until=body.until, after=body.after,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/list", tags=["Typeform"])
async def list_workspaces(body: TypeformAgentRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_workspaces(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/get", tags=["Typeform"])
async def get_workspace(body: TypeformWorkspaceIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_workspace(db, body.agent_id, body.workspace_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
