"""Notion endpoints router."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    NotionSearchRequest,
    NotionCreatePageRequest,
    NotionUpdatePageRequest,
    NotionAppendBlockChildrenRequest,
    NotionUpdateBlockRequest,
    NotionCreateDatabaseRequest,
    NotionQueryDatabaseRequest,
    NotionUpdateDatabaseRequest,
    NotionCreateCommentRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.post("/search", tags=["Notion"])
async def search(body: NotionSearchRequest, db: Session = Depends(get_db)):
    """Search pages and databases in the workspace."""
    try:
        return await service.search(
            db, body.agent_id,
            query=body.query, filter=body.filter, sort=body.sort,
            start_cursor=body.start_cursor, page_size=body.page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.post("/pages", tags=["Notion"])
async def create_page(body: NotionCreatePageRequest, db: Session = Depends(get_db)):
    """Create a new page."""
    try:
        return await service.create_page(
            db, body.agent_id,
            parent=body.parent, properties=body.properties,
            children=body.children, icon=body.icon, cover=body.cover,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{page_id}", tags=["Notion"])
async def get_page(agent_id: str, page_id: str, db: Session = Depends(get_db)):
    """Retrieve a page by ID."""
    try:
        return await service.get_page(db, agent_id, page_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/pages/{page_id}", tags=["Notion"])
async def update_page(page_id: str, body: NotionUpdatePageRequest, db: Session = Depends(get_db)):
    """Update page properties."""
    try:
        return await service.update_page(
            db, body.agent_id, page_id,
            properties=body.properties, archived=body.archived,
            icon=body.icon, cover=body.cover,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

@router.get("/blocks/{block_id}/children", tags=["Notion"])
async def get_block_children(
    agent_id: str, block_id: str,
    start_cursor: Optional[str] = None, page_size: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Retrieve block children (page content)."""
    try:
        return await service.get_block_children(
            db, agent_id, block_id,
            start_cursor=start_cursor, page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/blocks/{block_id}/children", tags=["Notion"])
async def append_block_children(
    block_id: str, body: NotionAppendBlockChildrenRequest,
    db: Session = Depends(get_db),
):
    """Append block children to a page or block."""
    try:
        return await service.append_block_children(
            db, body.agent_id, block_id,
            children=body.children, after=body.after,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/blocks/{block_id}", tags=["Notion"])
async def update_block(
    block_id: str, body: NotionUpdateBlockRequest,
    db: Session = Depends(get_db),
):
    """Update a block."""
    try:
        return await service.update_block(db, body.agent_id, block_id, body.block_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/blocks/{block_id}", tags=["Notion"])
async def delete_block(agent_id: str, block_id: str, db: Session = Depends(get_db)):
    """Delete (archive) a block."""
    try:
        return await service.delete_block(db, agent_id, block_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Databases
# ---------------------------------------------------------------------------

@router.post("/databases", tags=["Notion"])
async def create_database(body: NotionCreateDatabaseRequest, db: Session = Depends(get_db)):
    """Create a database."""
    try:
        return await service.create_database(
            db, body.agent_id,
            parent=body.parent, title=body.title, properties=body.properties,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}", tags=["Notion"])
async def get_database(agent_id: str, database_id: str, db: Session = Depends(get_db)):
    """Retrieve a database."""
    try:
        return await service.get_database(db, agent_id, database_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/databases/{database_id}/query", tags=["Notion"])
async def query_database(
    database_id: str, body: NotionQueryDatabaseRequest,
    db: Session = Depends(get_db),
):
    """Query a database."""
    try:
        return await service.query_database(
            db, body.agent_id, database_id,
            filter=body.filter, sorts=body.sorts,
            start_cursor=body.start_cursor, page_size=body.page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/databases/{database_id}", tags=["Notion"])
async def update_database(
    database_id: str, body: NotionUpdateDatabaseRequest,
    db: Session = Depends(get_db),
):
    """Update a database."""
    try:
        return await service.update_database(
            db, body.agent_id, database_id,
            title=body.title, properties=body.properties,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", tags=["Notion"])
async def list_users(agent_id: str, db: Session = Depends(get_db)):
    """List all users in workspace."""
    try:
        return await service.list_users(db, agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/me", tags=["Notion"])
async def get_bot_user(agent_id: str, db: Session = Depends(get_db)):
    """Get the bot user."""
    try:
        return await service.get_bot_user(db, agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}", tags=["Notion"])
async def get_user(agent_id: str, user_id: str, db: Session = Depends(get_db)):
    """Retrieve a user by ID."""
    try:
        return await service.get_user(db, agent_id, user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@router.post("/comments", tags=["Notion"])
async def create_comment(body: NotionCreateCommentRequest, db: Session = Depends(get_db)):
    """Create a comment on a page or discussion."""
    try:
        return await service.create_comment(
            db, body.agent_id,
            rich_text=body.rich_text, parent=body.parent,
            discussion_id=body.discussion_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments", tags=["Notion"])
async def get_comments(
    agent_id: str, block_id: str,
    start_cursor: Optional[str] = None, page_size: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Retrieve comments for a block or page."""
    try:
        return await service.get_comments(
            db, agent_id, block_id,
            start_cursor=start_cursor, page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
