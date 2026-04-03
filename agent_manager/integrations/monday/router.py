"""Monday endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import MondayApiRequest

router = APIRouter()


@router.post("/request", tags=["Monday"])
async def api_request(body: MondayApiRequest, db: Session = Depends(get_db)):
    """Execute an API request against Monday."""
    try:
        return await service.api_request(
            db, body.agent_id, body.method, body.path,
            params=body.params, json_body=body.json_body, data=body.data,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
