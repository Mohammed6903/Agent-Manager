"""Google Calendar endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from agent_manager.integrations.google.schemas import CreateEventRequest, UpdateEventRequest

router = APIRouter()

@router.get("/events", tags=["Google Calendar"])
def list_calendar_events(agent_id: str, max_results: int = 10, db: Session = Depends(get_db)):
    """List upcoming calendar events."""
    try:
        events = calendar_service.list_events(db, agent_id, max_results)
        if events is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"events": events}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/events/{event_id}", tags=["Google Calendar"])
def get_calendar_event(agent_id: str, event_id: str, db: Session = Depends(get_db)):
    """Get a specific calendar event."""
    try:
        event = calendar_service.get_event(db, agent_id, event_id)
        if event is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return event
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/events", tags=["Google Calendar"])
def create_calendar_event(body: CreateEventRequest, db: Session = Depends(get_db)):
    """Create a new calendar event."""
    try:
        event = calendar_service.create_event(
            db, body.agent_id,
            summary=body.summary,
            start_time=body.start_time,
            end_time=body.end_time,
            description=body.description,
            location=body.location,
            attendees=body.attendees,
            timezone=body.timezone,
            add_meet=body.add_meet,
        )
        if event is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"status": "created", "event": event}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/events/{event_id}", tags=["Google Calendar"])
def update_calendar_event(event_id: str, body: UpdateEventRequest, db: Session = Depends(get_db)):
    """Update an existing calendar event."""
    try:
        event = calendar_service.update_event(
            db, body.agent_id, event_id,
            summary=body.summary,
            start_time=body.start_time,
            end_time=body.end_time,
            description=body.description,
            location=body.location,
        )
        if event is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"status": "updated", "event": event}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/events/{event_id}", tags=["Google Calendar"])
def delete_calendar_event(agent_id: str, event_id: str, db: Session = Depends(get_db)):
    """Delete a calendar event."""
    try:
        result = calendar_service.delete_event(db, agent_id, event_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
