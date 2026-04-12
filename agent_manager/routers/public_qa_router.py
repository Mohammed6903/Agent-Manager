"""Public, unauthenticated Q&A endpoint.

Mounted at ``/api/public/qa`` in ``main.py``. Two endpoints:

- ``GET  /{agent_id}/info`` — public branding payload (title, subtitle,
  welcome message). Used by the visitor's browser to render the page
  before the first chat turn.
- ``POST /{agent_id}/chat`` — streaming SSE chat endpoint. Body carries
  the visitor's message + history + session_id.

**No auth in v1.** The endpoint's protections are layered inside the
backend handler:

1. Backend rate limiter (per-IP / per-agent / per-session) via
   ``qa_rate_limit.check_and_increment``.
2. ``agent_type == "qa"`` check (regular agents are NOT exposed here).
3. Soft-delete check.
4. Owner subscription + wallet gates inside ``qa_chat_service``.
5. ``tools=[]`` + guardian prompt + manual-context-only inside
   ``qa_chat_service``.
6. Output token cap.

Internal-secret hardening (an ``X-Internal-Api-Key`` header check) is
explicitly deferred — when added, it becomes a one-line ``Depends()``
on the router without changing any other logic in this file.
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.agent_registry import AGENT_TYPE_QA, AgentRegistry
from ..repositories.agent_registry_repository import AgentRegistryRepository
from ..services import qa_chat_service, qa_rate_limit

logger = logging.getLogger("agent_manager.routers.public_qa")

router = APIRouter()


# ── Request / response schemas (kept inline — they're tiny and only used here) ──


class _QAHistoryMessage(BaseModel):
    role: str
    content: str


class QAChatRequest(BaseModel):
    """Body sent by the visitor's browser on each chat turn.

    ``session_id`` is the visitor's localStorage-generated UUID. The
    backend rate limiter uses it for per-session turn counting; the
    chat service embeds it in the gateway's ``user`` field so the
    founder's usage dashboard can group turns by visitor.
    """

    message: str = Field(..., min_length=1, max_length=4000)
    history: list[_QAHistoryMessage] = Field(default_factory=list)
    session_id: str = Field(..., min_length=1, max_length=128)


class QAInfoResponse(BaseModel):
    agent_id: str
    title: str
    subtitle: Optional[str] = None
    welcome_message: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _get_client_ip(request: Request) -> str:
    """Extract the visitor's IP, preferring X-Forwarded-For when present.

    Trusts the first entry in XFF — that's the original client per the
    standard proxy convention. Falls back to the direct connection
    address. The returned string is the RAW ip; the caller is expected
    to hash it via ``qa_rate_limit.hash_client_ip`` before logging or
    storing it.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # First entry is the originating client; subsequent are proxy hops.
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _load_qa_agent(
    agent_id: str,
    db: Session,
) -> AgentRegistry:
    """Look up an agent by id, validate it's a Q&A agent, and return the row.

    Returns a generic 404 ("Assistant not found.") for any reason the
    agent isn't a usable public Q&A target — including agents that
    exist but aren't typed Q&A. We don't distinguish between "doesn't
    exist", "wrong type", or "soft-deleted" because all three are
    equivalent from the visitor's perspective and revealing the
    distinction would let an attacker enumerate which agents exist.
    """
    repo = AgentRegistryRepository(db)
    agent = repo.get(agent_id, include_deleted=False)
    if agent is None or agent.agent_type != AGENT_TYPE_QA:
        raise HTTPException(status_code=404, detail="Assistant not found.")
    return agent


# ── Endpoints ───────────────────────────────────────────────────────────────────


@router.get("/{agent_id}/info", response_model=QAInfoResponse, tags=["public-qa"])
async def get_qa_info(
    agent_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """Return the public branding payload for a Q&A agent.

    Lighter rate limit than ``/chat`` because this is a single
    page-load call, but still rate-limited so an attacker can't
    enumerate agents by hammering this endpoint. The session id is
    stubbed to ``"info"`` because page-info loads aren't part of a
    visitor conversation — only the per-IP and per-agent-day limits
    are meaningful here.
    """
    raw_ip = _get_client_ip(request)
    hashed_ip = qa_rate_limit.hash_client_ip(raw_ip)
    qa_rate_limit.check_and_increment(
        agent_id=agent_id,
        visitor_session_id="info",
        client_ip_hashed=hashed_ip,
    )
    agent = _load_qa_agent(agent_id, db)
    return QAInfoResponse(
        agent_id=agent.agent_id,
        title=agent.qa_page_title or agent.name,
        subtitle=agent.qa_page_subtitle,
        welcome_message=agent.qa_welcome_message,
    )


@router.post("/{agent_id}/chat", tags=["public-qa"])
async def post_qa_chat(
    agent_id: str,
    request: Request,
    body: Annotated[QAChatRequest, Body(...)],
    db: Annotated[Session, Depends(get_db)],
):
    """Stream a Q&A chat response.

    Order of operations:
        1. Rate limit (raises 429 on excess).
        2. Load + validate the agent (raises 404 if not a Q&A agent).
        3. Delegate to ``qa_chat_service.qa_chat_stream``, which runs
           the owner subscription + wallet gates and opens the gateway
           stream with ``tools=[]`` + guardian prompt.
    """
    raw_ip = _get_client_ip(request)
    hashed_ip = qa_rate_limit.hash_client_ip(raw_ip)
    qa_rate_limit.check_and_increment(
        agent_id=agent_id,
        visitor_session_id=body.session_id,
        client_ip_hashed=hashed_ip,
    )
    agent = _load_qa_agent(agent_id, db)

    history_dicts = [{"role": m.role, "content": m.content} for m in body.history]

    return await qa_chat_service.qa_chat_stream(
        agent=agent,
        visitor_session_id=body.session_id,
        user_message=body.message,
        history=history_dicts,
        db=db,
    )
