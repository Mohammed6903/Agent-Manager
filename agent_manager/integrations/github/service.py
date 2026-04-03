"""GitHub operations service."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "github"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

async def get_authenticated_user(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/user")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------

async def list_repos(
    db: Session, agent_id: str,
    sort: Optional[str] = None, per_page: Optional[int] = None,
    page: Optional[int] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if sort is not None:
        params["sort"] = sort
    if per_page is not None:
        params["per_page"] = per_page
    if page is not None:
        params["page"] = page
    async with client:
        resp = await client.get(f"{client.base_url}/user/repos", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_repo(db: Session, agent_id: str, owner: str, repo: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/repos/{owner}/{repo}")
        resp.raise_for_status()
        return resp.json()


async def create_repo(
    db: Session, agent_id: str, name: str,
    description: Optional[str] = None, private: Optional[bool] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"name": name}
    if description is not None:
        payload["description"] = description
    if private is not None:
        payload["private"] = private
    async with client:
        resp = await client.post(f"{client.base_url}/user/repos", json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

async def list_issues(
    db: Session, agent_id: str, owner: str, repo: str,
    state: Optional[str] = None, labels: Optional[str] = None,
    per_page: Optional[int] = None, page: Optional[int] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if state is not None:
        params["state"] = state
    if labels is not None:
        params["labels"] = labels
    if per_page is not None:
        params["per_page"] = per_page
    if page is not None:
        params["page"] = page
    async with client:
        resp = await client.get(f"{client.base_url}/repos/{owner}/{repo}/issues", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_issue(db: Session, agent_id: str, owner: str, repo: str, issue_number: int):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/repos/{owner}/{repo}/issues/{issue_number}")
        resp.raise_for_status()
        return resp.json()


async def create_issue(
    db: Session, agent_id: str, owner: str, repo: str,
    title: str, body: Optional[str] = None,
    labels: Optional[List[str]] = None, assignees: Optional[List[str]] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"title": title}
    if body is not None:
        payload["body"] = body
    if labels is not None:
        payload["labels"] = labels
    if assignees is not None:
        payload["assignees"] = assignees
    async with client:
        resp = await client.post(f"{client.base_url}/repos/{owner}/{repo}/issues", json=payload)
        resp.raise_for_status()
        return resp.json()


async def update_issue(
    db: Session, agent_id: str, owner: str, repo: str, issue_number: int,
    title: Optional[str] = None, body: Optional[str] = None,
    state: Optional[str] = None, labels: Optional[List[str]] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if labels is not None:
        payload["labels"] = labels
    async with client:
        resp = await client.patch(f"{client.base_url}/repos/{owner}/{repo}/issues/{issue_number}", json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Pull Requests
# ---------------------------------------------------------------------------

async def list_pull_requests(
    db: Session, agent_id: str, owner: str, repo: str,
    state: Optional[str] = None, per_page: Optional[int] = None,
    page: Optional[int] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if state is not None:
        params["state"] = state
    if per_page is not None:
        params["per_page"] = per_page
    if page is not None:
        params["page"] = page
    async with client:
        resp = await client.get(f"{client.base_url}/repos/{owner}/{repo}/pulls", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_pull_request(db: Session, agent_id: str, owner: str, repo: str, pull_number: int):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/repos/{owner}/{repo}/pulls/{pull_number}")
        resp.raise_for_status()
        return resp.json()


async def create_pull_request(
    db: Session, agent_id: str, owner: str, repo: str,
    title: str, head: str, base: str,
    body: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"title": title, "head": head, "base": base}
    if body is not None:
        payload["body"] = body
    async with client:
        resp = await client.post(f"{client.base_url}/repos/{owner}/{repo}/pulls", json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_repos(db: Session, agent_id: str, q: str, per_page: Optional[int] = None, page: Optional[int] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {"q": q}
    if per_page is not None:
        params["per_page"] = per_page
    if page is not None:
        params["page"] = page
    async with client:
        resp = await client.get(f"{client.base_url}/search/repositories", params=params)
        resp.raise_for_status()
        return resp.json()


async def search_issues(db: Session, agent_id: str, q: str, per_page: Optional[int] = None, page: Optional[int] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {"q": q}
    if per_page is not None:
        params["per_page"] = per_page
    if page is not None:
        params["page"] = page
    async with client:
        resp = await client.get(f"{client.base_url}/search/issues", params=params)
        resp.raise_for_status()
        return resp.json()


async def search_code(db: Session, agent_id: str, q: str, per_page: Optional[int] = None, page: Optional[int] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {"q": q}
    if per_page is not None:
        params["per_page"] = per_page
    if page is not None:
        params["page"] = page
    async with client:
        resp = await client.get(f"{client.base_url}/search/code", params=params)
        resp.raise_for_status()
        return resp.json()
