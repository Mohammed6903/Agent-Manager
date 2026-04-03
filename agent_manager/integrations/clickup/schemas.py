"""Pydantic request schemas for ClickUp endpoints."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ClickUpAgentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")


class ClickUpTeamIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    team_id: str = Field(..., description="Team/workspace ID.")


class ClickUpSpaceIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    space_id: str = Field(..., description="Space ID.")


class ClickUpCreateSpaceRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    team_id: str = Field(..., description="Team ID.")
    name: str = Field(..., description="Space name.")


class ClickUpFolderIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    folder_id: str = Field(..., description="Folder ID.")


class ClickUpCreateFolderRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    space_id: str = Field(..., description="Space ID.")
    name: str = Field(..., description="Folder name.")


class ClickUpListIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    list_id: str = Field(..., description="List ID.")


class ClickUpCreateListRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    folder_id: str = Field(..., description="Folder ID.")
    name: str = Field(..., description="List name.")


class ClickUpTaskIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    task_id: str = Field(..., description="Task ID.")


class ClickUpCreateTaskRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    list_id: str = Field(..., description="List ID to create the task in.")
    name: str = Field(..., description="Task name.")
    description: Optional[str] = Field(None, description="Task description (markdown).")
    assignees: Optional[List[int]] = Field(None, description="User IDs to assign.")
    priority: Optional[int] = Field(None, description="Priority (1=urgent, 2=high, 3=normal, 4=low).")
    due_date: Optional[int] = Field(None, description="Due date as Unix timestamp (ms).")
    status: Optional[str] = Field(None, description="Task status name.")


class ClickUpUpdateTaskRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    name: Optional[str] = Field(None, description="Updated task name.")
    description: Optional[str] = Field(None, description="Updated description.")
    priority: Optional[int] = Field(None, description="Updated priority.")
    due_date: Optional[int] = Field(None, description="Updated due date (Unix ms).")
    status: Optional[str] = Field(None, description="Updated status.")


class ClickUpCreateCommentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the ClickUp integration assigned.")
    task_id: str = Field(..., description="Task ID.")
    comment_text: str = Field(..., description="Comment text.")
