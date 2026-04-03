from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service


class GoogleAnalyticsApiRequest(BaseModel):
    agent_id: str = Field(..., description="Agent with Google Analytics integration")
    resource: str = Field(..., description="API resource path (e.g. presentations, forms, channels)")
    method: str = Field(..., description="Method to call on the resource (e.g. list, get, create)")
    params: Optional[Dict[str, Any]] = Field(None, description="Parameters to pass to the method")
    body: Optional[Dict[str, Any]] = Field(None, description="Request body")


router = APIRouter()


@router.post("/request", tags=["Google Analytics"])
def api_request(req: GoogleAnalyticsApiRequest, db: Session = Depends(get_db)):
    """Execute a Google Analytics API request via Google SDK."""
    try:
        svc = service.get_service(db, req.agent_id)
        if svc is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated with Google")

        # Navigate to the resource (e.g. svc.presentations() or svc.forms())
        resource_obj = svc
        for part in req.resource.split("."):
            resource_obj = getattr(resource_obj, part)()

        # Build the method call
        method_fn = getattr(resource_obj, req.method)

        kwargs = {}
        if req.params:
            kwargs.update(req.params)
        if req.body:
            kwargs["body"] = req.body

        result = method_fn(**kwargs).execute()
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
