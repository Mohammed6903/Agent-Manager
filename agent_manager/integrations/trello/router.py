"""Trello endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    TrelloAgentRequest,
    TrelloBoardRequest,
    TrelloCreateBoardRequest,
    TrelloCreateListRequest,
    TrelloUpdateListRequest,
    TrelloListCardsRequest,
    TrelloCardRequest,
    TrelloCreateCardRequest,
    TrelloUpdateCardRequest,
    TrelloCreateChecklistRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------

@router.post("/boards/list", tags=["Trello"])
async def list_boards(body: TrelloAgentRequest, db: Session = Depends(get_db)):
    """List boards for the authenticated member."""
    try:
        return await service.list_boards(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/boards/get", tags=["Trello"])
async def get_board(body: TrelloBoardRequest, db: Session = Depends(get_db)):
    """Get a board."""
    try:
        return await service.get_board(db, body.agent_id, body.board_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/boards/create", tags=["Trello"])
async def create_board(body: TrelloCreateBoardRequest, db: Session = Depends(get_db)):
    """Create a new board."""
    try:
        return await service.create_board(db, body.agent_id, body.name, desc=body.desc)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

@router.post("/boards/lists", tags=["Trello"])
async def get_board_lists(body: TrelloBoardRequest, db: Session = Depends(get_db)):
    """Get lists on a board."""
    try:
        return await service.get_board_lists(db, body.agent_id, body.board_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lists/create", tags=["Trello"])
async def create_list(body: TrelloCreateListRequest, db: Session = Depends(get_db)):
    """Create a new list."""
    try:
        return await service.create_list(db, body.agent_id, body.name, body.id_board)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/lists/{list_id}", tags=["Trello"])
async def update_list(list_id: str, body: TrelloUpdateListRequest, db: Session = Depends(get_db)):
    """Update a list."""
    try:
        return await service.update_list(db, body.agent_id, list_id, name=body.name, closed=body.closed)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

@router.post("/lists/cards", tags=["Trello"])
async def get_list_cards(body: TrelloListCardsRequest, db: Session = Depends(get_db)):
    """Get cards on a list."""
    try:
        return await service.get_list_cards(db, body.agent_id, body.list_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cards/get", tags=["Trello"])
async def get_card(body: TrelloCardRequest, db: Session = Depends(get_db)):
    """Get a card."""
    try:
        return await service.get_card(db, body.agent_id, body.card_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cards/create", tags=["Trello"])
async def create_card(body: TrelloCreateCardRequest, db: Session = Depends(get_db)):
    """Create a new card."""
    try:
        return await service.create_card(db, body.agent_id, body.id_list, name=body.name, desc=body.desc)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/cards/{card_id}", tags=["Trello"])
async def update_card(card_id: str, body: TrelloUpdateCardRequest, db: Session = Depends(get_db)):
    """Update a card."""
    try:
        return await service.update_card(
            db, body.agent_id, card_id,
            name=body.name, desc=body.desc, id_list=body.id_list, closed=body.closed,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cards/{card_id}", tags=["Trello"])
async def delete_card(agent_id: str, card_id: str, db: Session = Depends(get_db)):
    """Delete a card."""
    try:
        return await service.delete_card(db, agent_id, card_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@router.post("/members/me", tags=["Trello"])
async def get_me(body: TrelloAgentRequest, db: Session = Depends(get_db)):
    """Get the authenticated member."""
    try:
        return await service.get_me(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

@router.post("/boards/labels", tags=["Trello"])
async def get_board_labels(body: TrelloBoardRequest, db: Session = Depends(get_db)):
    """Get labels on a board."""
    try:
        return await service.get_board_labels(db, body.agent_id, body.board_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Checklists
# ---------------------------------------------------------------------------

@router.post("/checklists/create", tags=["Trello"])
async def create_checklist(body: TrelloCreateChecklistRequest, db: Session = Depends(get_db)):
    """Create a checklist on a card."""
    try:
        return await service.create_checklist(db, body.agent_id, body.id_card, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cards/checklists", tags=["Trello"])
async def get_card_checklists(body: TrelloCardRequest, db: Session = Depends(get_db)):
    """Get checklists on a card."""
    try:
        return await service.get_card_checklists(db, body.agent_id, body.card_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
