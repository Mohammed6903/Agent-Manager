"""GitHub endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    GitHubListReposRequest,
    GitHubRepoRequest,
    GitHubCreateRepoRequest,
    GitHubListIssuesRequest,
    GitHubCreateIssueRequest,
    GitHubUpdateIssueRequest,
    GitHubListPullsRequest,
    GitHubCreatePullRequest,
    GitHubSearchRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

@router.get("/user", tags=["GitHub"])
async def get_authenticated_user(agent_id: str, db: Session = Depends(get_db)):
    """Get the authenticated user."""
    try:
        return await service.get_authenticated_user(db, agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------

@router.post("/repos/list", tags=["GitHub"])
async def list_repos(body: GitHubListReposRequest, db: Session = Depends(get_db)):
    """List repositories for the authenticated user."""
    try:
        return await service.list_repos(db, body.agent_id, sort=body.sort, per_page=body.per_page, page=body.page)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/repos/get", tags=["GitHub"])
async def get_repo(body: GitHubRepoRequest, db: Session = Depends(get_db)):
    """Get a repository."""
    try:
        return await service.get_repo(db, body.agent_id, body.owner, body.repo)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/repos/create", tags=["GitHub"])
async def create_repo(body: GitHubCreateRepoRequest, db: Session = Depends(get_db)):
    """Create a repository."""
    try:
        return await service.create_repo(db, body.agent_id, body.name, description=body.description, private=body.private)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

@router.post("/issues/list", tags=["GitHub"])
async def list_issues(body: GitHubListIssuesRequest, db: Session = Depends(get_db)):
    """List issues for a repository."""
    try:
        return await service.list_issues(
            db, body.agent_id, body.owner, body.repo,
            state=body.state, labels=body.labels, per_page=body.per_page, page=body.page,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/repos/{owner}/{repo}/issues/{issue_number}", tags=["GitHub"])
async def get_issue(agent_id: str, owner: str, repo: str, issue_number: int, db: Session = Depends(get_db)):
    """Get an issue."""
    try:
        return await service.get_issue(db, agent_id, owner, repo, issue_number)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/issues/create", tags=["GitHub"])
async def create_issue(body: GitHubCreateIssueRequest, db: Session = Depends(get_db)):
    """Create an issue."""
    try:
        return await service.create_issue(
            db, body.agent_id, body.owner, body.repo,
            body.title, body=body.body, labels=body.labels, assignees=body.assignees,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/issues/update", tags=["GitHub"])
async def update_issue(body: GitHubUpdateIssueRequest, issue_number: int, db: Session = Depends(get_db)):
    """Update an issue."""
    try:
        return await service.update_issue(
            db, body.agent_id, body.owner, body.repo, issue_number,
            title=body.title, body=body.body, state=body.state, labels=body.labels,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Pull Requests
# ---------------------------------------------------------------------------

@router.post("/pulls/list", tags=["GitHub"])
async def list_pull_requests(body: GitHubListPullsRequest, db: Session = Depends(get_db)):
    """List pull requests."""
    try:
        return await service.list_pull_requests(
            db, body.agent_id, body.owner, body.repo,
            state=body.state, per_page=body.per_page, page=body.page,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/repos/{owner}/{repo}/pulls/{pull_number}", tags=["GitHub"])
async def get_pull_request(agent_id: str, owner: str, repo: str, pull_number: int, db: Session = Depends(get_db)):
    """Get a pull request."""
    try:
        return await service.get_pull_request(db, agent_id, owner, repo, pull_number)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pulls/create", tags=["GitHub"])
async def create_pull_request(body: GitHubCreatePullRequest, db: Session = Depends(get_db)):
    """Create a pull request."""
    try:
        return await service.create_pull_request(
            db, body.agent_id, body.owner, body.repo,
            body.title, body.head, body.base, body=body.body,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.post("/search/repositories", tags=["GitHub"])
async def search_repos(body: GitHubSearchRequest, db: Session = Depends(get_db)):
    """Search repositories."""
    try:
        return await service.search_repos(db, body.agent_id, body.q, per_page=body.per_page, page=body.page)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/issues", tags=["GitHub"])
async def search_issues(body: GitHubSearchRequest, db: Session = Depends(get_db)):
    """Search issues and pull requests."""
    try:
        return await service.search_issues(db, body.agent_id, body.q, per_page=body.per_page, page=body.page)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/code", tags=["GitHub"])
async def search_code(body: GitHubSearchRequest, db: Session = Depends(get_db)):
    """Search code."""
    try:
        return await service.search_code(db, body.agent_id, body.q, per_page=body.per_page, page=body.page)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
