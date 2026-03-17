from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from agent_manager.database import get_db
from agent_manager.integrations.google.schemas import CreateMeetSpaceRequest

from . import service as meet_service

router = APIRouter()

@router.post("/spaces", tags=["Google Meet"])
def create_meet_space(body: CreateMeetSpaceRequest, db: Session = Depends(get_db)):
    """Generate a new Google Meet space/link."""
    try:
        result = meet_service.create_space(db, body.agent_id, body.config)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/spaces/{space_id}", tags=["Google Meet"])
def get_meet_space(agent_id: str, space_id: str, db: Session = Depends(get_db)):
    """Retrieve details for an existing Meet space."""
    try:
        result = meet_service.get_space(db, agent_id, space_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))