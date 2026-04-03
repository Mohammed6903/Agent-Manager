from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import MicrosoftTeamsApiRequest

router = APIRouter()


@router.post("/request", tags=["Microsoft Teams"])
async def api_request(body: MicrosoftTeamsApiRequest, db: Session = Depends(get_db)):
    try:
        return await service.api_request(
            db, body.agent_id, body.method, body.path,
            params=body.params, json_body=body.json_body,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
