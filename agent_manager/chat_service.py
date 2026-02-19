"""Chat proxy — streams requests to the OpenClaw Gateway."""

from __future__ import annotations

import logging
import time
from typing import AsyncGenerator

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from .config import settings
from .schemas import ChatRequest, NewSessionResponse

logger = logging.getLogger("agent_manager.chat_service")

# Generous timeout for long LLM generations.
_HTTPX_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)


def _build_user_field(agent_id: str, user_id: str, session_id: str | None) -> str:
    if session_id:
        return f"{agent_id}:{user_id}:{session_id}"
    return f"{agent_id}:{user_id}"


async def _stream_gateway(req: ChatRequest) -> AsyncGenerator[bytes, None]:
    """Open a streaming connection to the OpenClaw Gateway and yield SSE chunks."""
    user_field = _build_user_field(req.agent_id, req.user_id, req.session_id)

    messages = [{"role": m.role, "content": m.content} for m in req.history]
    messages.append({"role": "user", "content": req.message})

    body = {
        "model": f"openclaw:{req.agent_id}",
        "messages": messages,
        "stream": True,
        "user": user_field,
    }

    headers = {
        "Content-Type": "application/json",
        "x-openclaw-agent-id": req.agent_id,
    }
    if settings.OPENCLAW_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {settings.OPENCLAW_GATEWAY_TOKEN}"

    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as client:
        try:
            async with client.stream(
                "POST",
                f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                json=body,
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    logger.error(
                        "Gateway returned %s: %s", resp.status_code, error_body.decode()[:500]
                    )
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail={
                            "error": "gateway_upstream_error",
                            "message": f"OpenClaw Gateway returned HTTP {resp.status_code}",
                            "gateway_url": f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                            "agent_id": req.agent_id,
                            "gateway_response": error_body.decode()[:500],
                        },
                    )
                async for chunk in resp.aiter_bytes():
                    yield chunk
        except httpx.ConnectError as exc:
            logger.error("Cannot connect to OpenClaw Gateway: %s", exc)
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "gateway_connection_error",
                    "message": "Cannot connect to OpenClaw Gateway",
                    "gateway_url": settings.OPENCLAW_GATEWAY_URL,
                    "hint": "Is the OpenClaw gateway running? Check with: openclaw gateway status",
                    "original_error": str(exc),
                },
            )


async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Return a streaming SSE response proxied from the gateway."""
    return StreamingResponse(
        _stream_gateway(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
        },
    )


async def chat_non_stream(req: ChatRequest) -> dict:
    """Send a non-streaming chat request and return the full response."""
    user_field = _build_user_field(req.agent_id, req.user_id, req.session_id)

    messages = [{"role": m.role, "content": m.content} for m in req.history]
    messages.append({"role": "user", "content": req.message})

    body = {
        "model": f"openclaw:{req.agent_id}",
        "messages": messages,
        "stream": False,
        "user": user_field,
    }

    headers = {
        "Content-Type": "application/json",
        "x-openclaw-agent-id": req.agent_id,
    }
    if settings.OPENCLAW_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {settings.OPENCLAW_GATEWAY_TOKEN}"

    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                json=body,
                headers=headers,
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail={
                        "error": "gateway_upstream_error",
                        "message": f"OpenClaw Gateway returned HTTP {resp.status_code}",
                        "gateway_url": f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                        "agent_id": req.agent_id,
                        "gateway_response": resp.text[:500],
                    },
                )
            data = resp.json()
            # Extract assistant content from OpenAI-compatible response
            content = ""
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content", "")
            return {"response": content, "raw": data}
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "gateway_connection_error",
                    "message": "Cannot connect to OpenClaw Gateway",
                    "gateway_url": settings.OPENCLAW_GATEWAY_URL,
                    "hint": "Is the OpenClaw gateway running? Check with: openclaw gateway status",
                    "original_error": str(exc),
                },
            )


def new_session() -> NewSessionResponse:
    """Generate a timestamp-based session ID."""
    return NewSessionResponse(session_id=str(int(time.time())))
