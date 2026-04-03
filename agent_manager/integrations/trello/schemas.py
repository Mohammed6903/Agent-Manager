"""Pydantic request schemas for Trello endpoints."""

from typing import Optional
from pydantic import BaseModel, Field


class TrelloAgentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")


class TrelloBoardRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    board_id: str = Field(..., description="Board ID.")


class TrelloCreateBoardRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    name: str = Field(..., description="Board name.")
    desc: Optional[str] = Field(None, description="Board description.")


class TrelloCreateListRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    name: str = Field(..., description="List name.")
    id_board: str = Field(..., description="Board ID to create the list in.")


class TrelloUpdateListRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    name: Optional[str] = Field(None, description="Updated list name.")
    closed: Optional[bool] = Field(None, description="Whether to archive the list.")


class TrelloListCardsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    list_id: str = Field(..., description="List ID.")


class TrelloCardRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    card_id: str = Field(..., description="Card ID.")


class TrelloCreateCardRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    id_list: str = Field(..., description="List ID to create the card in.")
    name: Optional[str] = Field(None, description="Card name.")
    desc: Optional[str] = Field(None, description="Card description.")


class TrelloUpdateCardRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    name: Optional[str] = Field(None, description="Updated card name.")
    desc: Optional[str] = Field(None, description="Updated card description.")
    id_list: Optional[str] = Field(None, description="Move card to this list.")
    closed: Optional[bool] = Field(None, description="Whether to archive the card.")


class TrelloCreateChecklistRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Trello integration assigned.")
    id_card: str = Field(..., description="Card ID to create checklist on.")
    name: str = Field(..., description="Checklist name.")
