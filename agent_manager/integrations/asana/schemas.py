"""Pydantic request schemas for Asana endpoints."""

from typing import List, Optional
from pydantic import BaseModel, Field


class AsanaAgentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")


class AsanaWorkspaceUsersRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    workspace: str = Field(..., description="Workspace GID.")


class AsanaListProjectsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    workspace: Optional[str] = Field(None, description="Workspace GID to filter by.")
    archived: Optional[bool] = Field(None, description="Filter by archived status.")


class AsanaProjectRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    project_gid: str = Field(..., description="Project GID.")


class AsanaCreateProjectRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    workspace: str = Field(..., description="Workspace GID.")
    name: str = Field(..., description="Project name.")
    notes: Optional[str] = Field(None, description="Project description.")


class AsanaListTasksRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    project_gid: str = Field(..., description="Project GID.")
    completed_since: Optional[str] = Field(None, description="ISO 8601 date to filter completed tasks.")


class AsanaTaskRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    task_gid: str = Field(..., description="Task GID.")


class AsanaCreateTaskRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    name: str = Field(..., description="Task name.")
    projects: Optional[List[str]] = Field(None, description="Project GIDs to add the task to.")
    workspace: Optional[str] = Field(None, description="Workspace GID (required if projects not set).")
    notes: Optional[str] = Field(None, description="Task description.")
    assignee: Optional[str] = Field(None, description="Assignee GID or 'me'.")
    due_on: Optional[str] = Field(None, description="Due date (YYYY-MM-DD).")


class AsanaUpdateTaskRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    name: Optional[str] = Field(None, description="Updated task name.")
    completed: Optional[bool] = Field(None, description="Mark as completed.")
    notes: Optional[str] = Field(None, description="Updated description.")
    assignee: Optional[str] = Field(None, description="Updated assignee GID.")
    due_on: Optional[str] = Field(None, description="Updated due date.")


class AsanaCreateSectionRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Asana integration assigned.")
    project_gid: str = Field(..., description="Project GID.")
    name: str = Field(..., description="Section name.")
