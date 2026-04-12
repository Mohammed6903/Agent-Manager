"""Agent-type guardrails for tool-invocation HTTP endpoints.

These helpers enforce a simple rule: **agents typed ``qa`` must not be
able to execute state-changing tools.** They exist because the OpenClaw
gateway's plugin system registers tool endpoints (task tracking,
garage feed, integration writes, etc.) per-agent based on the agent's
plugin config — NOT based on what ``qa_chat_service`` passes in the
request body's ``tools`` field. So the LLM on a Q&A path can still
emit a ``task_create`` / ``create_garage_post`` / whatever tool call,
and the gateway will happily POST it to the corresponding OpenClawApi
HTTP endpoint. The request reaches FastAPI with the same ``agent_id``
in the body, and unless we reject it at the endpoint, it succeeds.

This module is that rejection layer. Endpoints that perform write
actions triggered by agent tool calls should run ``assert_non_qa_agent``
(or use the ``require_non_qa_agent_dep`` FastAPI dependency) before
executing, so a Q&A-typed agent — which is supposed to be read-only
Q&A — cannot create tasks, post to feeds, or otherwise mutate state.

Reads are NOT guarded: a Q&A agent legitimately needs to read its own
assigned contexts to answer questions, and reading ``/api/tasks`` does
nothing harmful. Only write methods (POST/PATCH/PUT/DELETE that change
state visible to the founder or third parties) need protection.

The check is cheap — one indexed Postgres lookup — but we still avoid
calling it in hot paths if the endpoint is read-only.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.agent_registry import AGENT_TYPE_QA
from ..repositories.agent_registry_repository import AgentRegistryRepository

logger = logging.getLogger(__name__)


def assert_non_qa_agent(db: Session, agent_id: str, action: str) -> None:
    """Raise HTTPException(403) if ``agent_id`` is a Q&A-typed agent.

    ``action`` is a short human-readable label for the attempted
    operation (``"create task"``, ``"post to feed"``, etc). It's
    included in the log line so an operator watching FastAPI logs can
    see exactly which Q&A agent tried to do what — a strong signal
    that someone is prompt-injecting the public endpoint.

    Safe to call on a missing agent_id — we let the caller handle 404
    for "agent not found" separately, so this just returns cleanly if
    the lookup doesn't find anything. The worst case is the caller's
    normal validation catches it instead of us, which is fine.
    """
    if not agent_id:
        return
    try:
        repo = AgentRegistryRepository(db)
        agent = repo.get(agent_id, include_deleted=True)
    except Exception:
        # Registry lookup failed — don't silently allow, but also
        # don't block legitimate traffic on a transient DB error.
        # Log and let the normal endpoint validation decide.
        logger.exception(
            "agent_guard: registry lookup failed for agent_id=%s action=%s",
            agent_id,
            action,
        )
        return
    if agent is not None and agent.agent_type == AGENT_TYPE_QA:
        logger.warning(
            "agent_guard: REJECTED %s — agent_id=%s is type=qa (public Q&A) "
            "and cannot invoke write tools",
            action,
            agent_id,
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"Agent '{agent_id}' is a public Q&A assistant and is not "
                f"permitted to {action}."
            ),
        )
