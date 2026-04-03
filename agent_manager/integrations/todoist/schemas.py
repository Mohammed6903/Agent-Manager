"""Pydantic request schemas for Todoist endpoints."""

from typing import List, Optional
from pydantic import BaseModel, Field


class TodoistAgentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")


class TodoistProjectIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    project_id: str = Field(..., description="Project ID.")


class TodoistCreateProjectRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    name: str = Field(..., description="Project name.")
    parent_id: Optional[str] = Field(None, description="Parent project ID for nesting.")


class TodoistUpdateProjectRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    name: Optional[str] = Field(None, description="Updated project name.")


class TodoistListTasksRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    project_id: Optional[str] = Field(None, description="Filter by project ID.")
    label: Optional[str] = Field(None, description="Filter by label name.")


class TodoistTaskIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    task_id: str = Field(..., description="Task ID.")


class TodoistCreateTaskRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    content: str = Field(..., description="Task content/title.")
    project_id: Optional[str] = Field(None, description="Project ID.")
    description: Optional[str] = Field(None, description="Task description.")
    due_string: Optional[str] = Field(None, description="Natural language due date (e.g. 'tomorrow', 'every friday').")
    priority: Optional[int] = Field(None, description="Priority (1=normal, 4=urgent).")
    labels: Optional[List[str]] = Field(None, description="Label names.")


class TodoistUpdateTaskRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    content: Optional[str] = Field(None, description="Updated content.")
    description: Optional[str] = Field(None, description="Updated description.")
    due_string: Optional[str] = Field(None, description="Updated due date.")
    priority: Optional[int] = Field(None, description="Updated priority.")


class TodoistListCommentsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    task_id: Optional[str] = Field(None, description="Task ID (required if no project_id).")
    project_id: Optional[str] = Field(None, description="Project ID (required if no task_id).")


class TodoistCreateCommentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    content: str = Field(..., description="Comment content (markdown).")
    task_id: Optional[str] = Field(None, description="Task ID.")
    project_id: Optional[str] = Field(None, description="Project ID.")


class TodoistCreateLabelRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    name: str = Field(..., description="Label name.")


class TodoistCreateSectionRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Todoist integration assigned.")
    project_id: str = Field(..., description="Project ID.")
    name: str = Field(..., description="Section name.")
