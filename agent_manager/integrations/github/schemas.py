"""Pydantic request schemas for GitHub endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GitHubListReposRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    sort: Optional[str] = Field(None, description="Sort by: created, updated, pushed, full_name.")
    per_page: Optional[int] = Field(None, description="Results per page (max 100).")
    page: Optional[int] = Field(None, description="Page number.")


class GitHubRepoRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    owner: str = Field(..., description="Repository owner (user or org).")
    repo: str = Field(..., description="Repository name.")


class GitHubCreateRepoRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    name: str = Field(..., description="Repository name.")
    description: Optional[str] = Field(None, description="Repository description.")
    private: Optional[bool] = Field(None, description="Whether the repo is private.")


class GitHubListIssuesRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    owner: str = Field(..., description="Repository owner.")
    repo: str = Field(..., description="Repository name.")
    state: Optional[str] = Field(None, description="Filter by state: open, closed, all.")
    labels: Optional[str] = Field(None, description="Comma-separated list of label names.")
    per_page: Optional[int] = Field(None, description="Results per page (max 100).")
    page: Optional[int] = Field(None, description="Page number.")


class GitHubCreateIssueRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    owner: str = Field(..., description="Repository owner.")
    repo: str = Field(..., description="Repository name.")
    title: str = Field(..., description="Issue title.")
    body: Optional[str] = Field(None, description="Issue body (markdown).")
    labels: Optional[List[str]] = Field(None, description="Labels to add.")
    assignees: Optional[List[str]] = Field(None, description="Usernames to assign.")


class GitHubUpdateIssueRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    owner: str = Field(..., description="Repository owner.")
    repo: str = Field(..., description="Repository name.")
    title: Optional[str] = Field(None, description="Updated title.")
    body: Optional[str] = Field(None, description="Updated body.")
    state: Optional[str] = Field(None, description="State: open or closed.")
    labels: Optional[List[str]] = Field(None, description="Updated labels.")


class GitHubListPullsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    owner: str = Field(..., description="Repository owner.")
    repo: str = Field(..., description="Repository name.")
    state: Optional[str] = Field(None, description="Filter by state: open, closed, all.")
    per_page: Optional[int] = Field(None, description="Results per page (max 100).")
    page: Optional[int] = Field(None, description="Page number.")


class GitHubCreatePullRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    owner: str = Field(..., description="Repository owner.")
    repo: str = Field(..., description="Repository name.")
    title: str = Field(..., description="Pull request title.")
    head: str = Field(..., description="Branch containing changes.")
    base: str = Field(..., description="Branch to merge into.")
    body: Optional[str] = Field(None, description="Pull request body.")


class GitHubSearchRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the GitHub integration assigned.")
    q: str = Field(..., description="Search query string.")
    per_page: Optional[int] = Field(None, description="Results per page (max 100).")
    page: Optional[int] = Field(None, description="Page number.")
