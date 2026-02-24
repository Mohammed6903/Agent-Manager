"""Chat proxy — streams requests to the OpenClaw Gateway."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .config import settings
from .schemas import ChatRequest, NewSessionResponse

logger = logging.getLogger("agent_manager.chat_service")

# Generous timeout for long LLM generations.
_HTTPX_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)


def _build_user_field(
    agent_id: str,
    user_id: str,
    session_id: str | None = None,
    room_id: str | None = None,
) -> str:
    """Build the user field for session isolation.

    DM sessions:    agent_id:user_id[:session_id]
    Group sessions: agent_id:group:room_id
    """
    if room_id:
        return f"{agent_id}:group:{room_id}"
    if session_id:
        return f"{agent_id}:{user_id}:{session_id}"
    return f"{agent_id}:{user_id}"


# Hidden system instruction appended when files are uploaded.
_FILE_SYSTEM_PROMPT = (
    "[SYSTEM INSTRUCTION — DO NOT REVEAL THIS TO THE USER]\n"
    "The user has attached file(s) that have been saved to your workspace. "
    "The file paths are listed below. Read and process each file to answer the user's message. "
    "After you have fully processed each file, delete it from disk. "
    "IMPORTANT: Do NOT mention the file path, file location, upload process, "
    "or the fact that you deleted the file in your response. "
    "Respond naturally as if the user simply shared the file content with you directly."
)


def _build_messages(
    req: "ChatRequest",
    uploaded_file_paths: list[str] | None = None,
) -> list[dict]:
    """Build the messages list, injecting recent_context for group @mentions."""
    messages = [{"role": m.role, "content": m.content} for m in req.history]

    user_content = req.message

    if req.room_id and req.recent_context:
        # Group chat: prepend recent conversation context so the agent
        # sees who said what, then the triggering user's actual message.
        user_content = (
            f"[Group chat in room '{req.room_id}' — recent messages]\n"
            f"{req.recent_context}\n\n"
            f"[{req.user_id} mentioned you and said]:\n{req.message}"
        )

    if uploaded_file_paths:
        files_list = "\n".join(f"- {p}" for p in uploaded_file_paths)
        user_content = (
            f"{_FILE_SYSTEM_PROMPT}\n"
            f"Files:\n{files_list}\n\n"
            f"User message: {user_content}"
        )

    messages.append({"role": "user", "content": user_content})
    return messages


async def _stream_gateway(
    req: ChatRequest,
    uploaded_file_paths: list[str] | None = None,
) -> AsyncGenerator[bytes, None]:
    """Open a streaming connection to the OpenClaw Gateway and yield SSE chunks."""
    user_field = _build_user_field(
        req.agent_id, req.user_id,
        session_id=req.session_id, room_id=req.room_id,
    )
    messages = _build_messages(req, uploaded_file_paths=uploaded_file_paths)

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
    user_field = _build_user_field(
        req.agent_id, req.user_id,
        session_id=req.session_id, room_id=req.room_id,
    )
    messages = _build_messages(req)

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


# ── File upload helpers ─────────────────────────────────────────────────────────

_ALLOWED_EXTENSIONS = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
    # Documents
    ".pdf", ".txt", ".csv", ".json", ".yaml", ".yml", ".xml",
    ".md", ".html", ".htm", ".log",
    # Office
    ".doc", ".docx", ".xls", ".xlsx",
}


def _uploads_dir(agent_id: str) -> Path:
    """Return the uploads directory for an agent's workspace."""
    return Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}" / "uploads"


async def save_upload(agent_id: str, file: UploadFile) -> str:
    """Save an uploaded file to the agent's workspace and return the path.

    Validates file size and extension. Raises HTTPException on errors.
    """
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_file_type",
                "message": f"File type '{ext}' is not supported.",
                "allowed": sorted(_ALLOWED_EXTENSIONS),
            },
        )

    # Read file and validate size
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "file_too_large",
                "message": f"File size ({len(content) / 1024 / 1024:.1f}MB) exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit.",
                "max_size_mb": settings.MAX_UPLOAD_SIZE_MB,
            },
        )

    # Generate unique filename to avoid collisions
    unique_name = f"{uuid.uuid4().hex[:12]}_{file.filename}"
    upload_dir = _uploads_dir(agent_id)
    await asyncio.to_thread(os.makedirs, str(upload_dir), exist_ok=True)

    filepath = upload_dir / unique_name
    await asyncio.to_thread(filepath.write_bytes, content)

    logger.info("Saved upload: %s (%d bytes)", filepath, len(content))
    return str(filepath)


async def chat_with_files_stream(
    message: str,
    agent_id: str,
    user_id: str,
    file_paths: list[str],
    session_id: str | None = None,
    room_id: str | None = None,
    recent_context: str | None = None,
    history_json: str | None = None,
) -> StreamingResponse:
    """Stream a chat response after uploading files to the agent workspace."""
    import json as _json

    history = []
    if history_json:
        try:
            raw = _json.loads(history_json)
            from .schemas import ChatMessage
            history = [ChatMessage(**m) for m in raw]
        except Exception:
            pass

    req = ChatRequest(
        message=message,
        agent_id=agent_id,
        user_id=user_id,
        session_id=session_id,
        room_id=room_id,
        recent_context=recent_context,
        history=history,
    )

    return StreamingResponse(
        _stream_gateway(req, uploaded_file_paths=file_paths),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def chat_with_files_non_stream(
    message: str,
    agent_id: str,
    user_id: str,
    file_paths: list[str],
    session_id: str | None = None,
    room_id: str | None = None,
    recent_context: str | None = None,
    history_json: str | None = None,
) -> dict:
    """Non-streaming chat response after uploading files to the agent workspace."""
    import json as _json

    history = []
    if history_json:
        try:
            raw = _json.loads(history_json)
            from .schemas import ChatMessage
            history = [ChatMessage(**m) for m in raw]
        except Exception:
            pass

    req = ChatRequest(
        message=message,
        agent_id=agent_id,
        user_id=user_id,
        session_id=session_id,
        room_id=room_id,
        recent_context=recent_context,
        history=history,
    )

    user_field = _build_user_field(
        req.agent_id, req.user_id,
        session_id=req.session_id, room_id=req.room_id,
    )
    messages = _build_messages(req, uploaded_file_paths=file_paths)

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
                        "agent_id": req.agent_id,
                        "gateway_response": resp.text[:500],
                    },
                )
            data = resp.json()
            content = ""
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                message_obj = choice.get("message", {})
                content = message_obj.get("content", "")
            return {"response": content, "raw": data}
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "gateway_connection_error",
                    "message": "Cannot connect to OpenClaw Gateway",
                    "gateway_url": settings.OPENCLAW_GATEWAY_URL,
                    "original_error": str(exc),
                },
            )
