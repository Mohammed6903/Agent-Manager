"""Airtable endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    AirtableAgentRequest,
    AirtableBaseRequest,
    AirtableListRecordsRequest,
    AirtableGetRecordRequest,
    AirtableCreateRecordsRequest,
    AirtableUpdateRecordsRequest,
    AirtableDeleteRecordsRequest,
)

router = APIRouter()


@router.post("/bases/list", tags=["Airtable"])
async def list_bases(body: AirtableAgentRequest, db: Session = Depends(get_db)):
    """List all accessible bases."""
    try:
        return await service.list_bases(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tables/list", tags=["Airtable"])
async def list_tables(body: AirtableBaseRequest, db: Session = Depends(get_db)):
    """List tables in a base."""
    try:
        return await service.list_tables(db, body.agent_id, body.base_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/records/list", tags=["Airtable"])
async def list_records(body: AirtableListRecordsRequest, db: Session = Depends(get_db)):
    """List records in a table."""
    try:
        return await service.list_records(
            db, body.agent_id, body.base_id, body.table_id_or_name,
            max_records=body.max_records, view=body.view,
            filter_by_formula=body.filter_by_formula, offset=body.offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/records/get", tags=["Airtable"])
async def get_record(body: AirtableGetRecordRequest, db: Session = Depends(get_db)):
    """Get a single record."""
    try:
        return await service.get_record(db, body.agent_id, body.base_id, body.table_id_or_name, body.record_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/records/create", tags=["Airtable"])
async def create_records(body: AirtableCreateRecordsRequest, db: Session = Depends(get_db)):
    """Create records in a table."""
    try:
        return await service.create_records(db, body.agent_id, body.base_id, body.table_id_or_name, body.records)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/records/update", tags=["Airtable"])
async def update_records(body: AirtableUpdateRecordsRequest, db: Session = Depends(get_db)):
    """Update records in a table."""
    try:
        return await service.update_records(db, body.agent_id, body.base_id, body.table_id_or_name, body.records)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/records/delete", tags=["Airtable"])
async def delete_records(body: AirtableDeleteRecordsRequest, db: Session = Depends(get_db)):
    """Delete records from a table."""
    try:
        return await service.delete_records(db, body.agent_id, body.base_id, body.table_id_or_name, body.record_ids)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
