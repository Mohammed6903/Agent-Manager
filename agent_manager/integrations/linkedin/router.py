"""LinkedIn endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import CreateUgcPostRequest, InitializeImageUploadRequest

router = APIRouter()

@router.get("/userinfo", tags=["LinkedIn"])
async def get_userinfo(agent_id: str, db: Session = Depends(get_db)):
    """Get the authenticated user's info."""
    try:
        result = await service.get_userinfo(db, agent_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/me", tags=["LinkedIn"])
async def get_me(agent_id: str, db: Session = Depends(get_db)):
    """Get the authenticated user's profile."""
    try:
        result = await service.get_me(db, agent_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ugcPosts", tags=["LinkedIn"])
async def create_ugc_post(body: CreateUgcPostRequest, db: Session = Depends(get_db)):
    """Create a new UGC post."""
    try:
        result = await service.create_ugc_post(db, body.agent_id, body.author_urn, body.text)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ugcPosts/{ugc_post_urn}", tags=["LinkedIn"])
async def get_ugc_post(agent_id: str, ugc_post_urn: str, db: Session = Depends(get_db)):
    """Get a specific UGC post by URN."""
    try:
        result = await service.get_ugc_post(db, agent_id, ugc_post_urn)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/ugcPosts/{ugc_post_urn}", tags=["LinkedIn"])
async def delete_ugc_post(agent_id: str, ugc_post_urn: str, db: Session = Depends(get_db)):
    """Delete a specific UGC post by URN."""
    try:
        result = await service.delete_ugc_post(db, agent_id, ugc_post_urn)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/connections", tags=["LinkedIn"])
async def get_connections(agent_id: str, db: Session = Depends(get_db)):
    """Get first-degree connections."""
    try:
        result = await service.get_connections(db, agent_id)
        return result
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/organizations", tags=["LinkedIn"])
async def get_organizations(agent_id: str, db: Session = Depends(get_db)):
    """Get organizational entity ACLs."""
    try:
        result = await service.get_organizations(db, agent_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/images/initialize", tags=["LinkedIn"])
async def initialize_image_upload(body: InitializeImageUploadRequest, db: Session = Depends(get_db)):
    """Initialize an image upload."""
    try:
        result = await service.initialize_image_upload(db, body.agent_id, body.person_urn)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))