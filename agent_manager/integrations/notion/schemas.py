"""Pydantic request schemas for Notion endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NotionSearchRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    query: Optional[str] = Field(None, description="Search query text.")
    filter: Optional[Dict[str, Any]] = Field(None, description="Filter object, e.g. {'value': 'page', 'property': 'object'}.")
    sort: Optional[Dict[str, Any]] = Field(None, description="Sort object, e.g. {'direction': 'descending', 'timestamp': 'last_edited_time'}.")
    start_cursor: Optional[str] = Field(None, description="Pagination cursor.")
    page_size: Optional[int] = Field(None, description="Number of results per page (max 100).")


class NotionCreatePageRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    parent: Dict[str, Any] = Field(..., description="Parent object, e.g. {'database_id': '...'} or {'page_id': '...'}.")
    properties: Dict[str, Any] = Field(..., description="Page properties matching the parent database schema.")
    children: Optional[List[Dict[str, Any]]] = Field(None, description="Page content as block objects.")
    icon: Optional[Dict[str, Any]] = Field(None, description="Icon object (emoji or external URL).")
    cover: Optional[Dict[str, Any]] = Field(None, description="Cover image object.")


class NotionUpdatePageRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    properties: Optional[Dict[str, Any]] = Field(None, description="Properties to update.")
    archived: Optional[bool] = Field(None, description="Set to true to archive (delete) the page.")
    icon: Optional[Dict[str, Any]] = Field(None, description="Icon object.")
    cover: Optional[Dict[str, Any]] = Field(None, description="Cover image object.")


class NotionAppendBlockChildrenRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    children: List[Dict[str, Any]] = Field(..., description="Array of block objects to append.")
    after: Optional[str] = Field(None, description="Block ID to append after.")


class NotionUpdateBlockRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    block_data: Dict[str, Any] = Field(..., description="Block type object with updated content, e.g. {'paragraph': {'rich_text': [...]}}.")


class NotionCreateDatabaseRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    parent: Dict[str, Any] = Field(..., description="Parent object, e.g. {'page_id': '...'}.")
    title: List[Dict[str, Any]] = Field(..., description="Database title as rich text array.")
    properties: Dict[str, Any] = Field(..., description="Property schema for the database.")


class NotionQueryDatabaseRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    filter: Optional[Dict[str, Any]] = Field(None, description="Filter object for the query.")
    sorts: Optional[List[Dict[str, Any]]] = Field(None, description="Sort criteria array.")
    start_cursor: Optional[str] = Field(None, description="Pagination cursor.")
    page_size: Optional[int] = Field(None, description="Number of results per page (max 100).")


class NotionUpdateDatabaseRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    title: Optional[List[Dict[str, Any]]] = Field(None, description="Updated database title as rich text array.")
    properties: Optional[Dict[str, Any]] = Field(None, description="Updated property schema.")


class NotionCreateCommentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Notion integration assigned.")
    parent: Optional[Dict[str, Any]] = Field(None, description="Parent page object, e.g. {'page_id': '...'}. Required if discussion_id is not set.")
    discussion_id: Optional[str] = Field(None, description="Discussion thread ID. Required if parent is not set.")
    rich_text: List[Dict[str, Any]] = Field(..., description="Comment content as rich text array.")
