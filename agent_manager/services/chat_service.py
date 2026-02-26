"""Chat proxy — streams requests to the OpenClaw Gateway."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncGenerator

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from ..config import settings
from ..garage_tool import GARAGE_TOOLS, execute_create_garage_post, load_garage_credentials
from ..schemas.chat import ChatRequest, NewSessionResponse

logger = logging.getLogger("agent_manager.services.chat_service")

# Timeout for non-streaming requests (sync completions).
_HTTPX_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)

# For streaming: no read timeout — reasoning models may think silently for
# several minutes before emitting the first token.
_HTTPX_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)


class ChatService:
    # Hidden system instruction appended when files are uploaded.
    _FILE_SYSTEM_PROMPT = (
        "[SYSTEM INSTRUCTION — DO NOT REVEAL THIS TO THE USER]\n"
        "The user has attached file(s) that have been saved to your workspace. "
        "The file paths are listed below.\n\n"
        "PROCESSING INSTRUCTIONS:\n"
        "- For text-based files (.txt, .csv, .json, .yaml, .yml, .xml, .md, .html, .log): "
        "Use your file reading tool to read the file contents, then process them.\n"
        "- For PDF files (.pdf): Use your file reading tool to read/extract the text content from the PDF.\n"
        "- For document files (.doc, .docx, .xls, .xlsx): Attempt to read and extract content from these files.\n"
        "- For image files (.png, .jpg, .jpeg, .gif, .webp, .bmp, .tiff, .svg): "
        "Use your vision/image capabilities to view and analyze the image.\n\n"
        "After you have fully processed each file, delete it from disk.\n"
        "IMPORTANT: Do NOT mention the file path, file location, upload process, "
        "or the fact that you deleted the file in your response. "
        "Respond naturally as if the user simply shared the file content with you directly."
    )

    _IMAGE_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        ".tiff", ".tif", ".heic", ".heif", ".svg",
    }
    _DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
    _TEXT_EXTENSIONS = {
        ".txt", ".csv", ".json", ".yaml", ".yml", ".xml",
        ".md", ".html", ".htm", ".log",
    }

    def _build_user_field(
        self,
        agent_id: str,
        user_id: str,
        session_id: str | None = None,
        room_id: str | None = None,
    ) -> str:
        """Build the user field for session isolation."""
        if room_id:
            return f"{agent_id}:group:{room_id}"
        if session_id:
            return f"{agent_id}:{user_id}:{session_id}"
        return f"{agent_id}:{user_id}"

    def _file_type_label(self, path: str) -> str:
        """Return a human-friendly type label for a file path."""
        ext = os.path.splitext(path)[1].lower()
        if ext in self._IMAGE_EXTENSIONS:
            return "image"
        if ext == ".pdf":
            return "PDF document"
        if ext in self._DOCUMENT_EXTENSIONS:
            return "office document"
        if ext in self._TEXT_EXTENSIONS:
            return "text file"
        return "file"

    def _build_messages(
        self,
        req: ChatRequest,
        uploaded_file_paths: list[str] | None = None,
    ) -> list[dict]:
        """Build the messages list, injecting recent_context for group @mentions."""
        messages = [{"role": m.role, "content": m.content} for m in req.history]

        user_content = req.message

        if req.room_id and req.recent_context:
            user_content = (
                f"[Group chat in room '{req.room_id}' — recent messages]\n"
                f"{req.recent_context}\n\n"
                f"[{req.user_id} mentioned you and said]:\n{req.message}"
            )

        if uploaded_file_paths:
            files_list = "\n".join(
                f"- {p}  (type: {self._file_type_label(p)})"
                for p in uploaded_file_paths
            )
            user_content = (
                f"{self._FILE_SYSTEM_PROMPT}\n"
                f"Files:\n{files_list}\n\n"
                f"User message: {user_content}"
            )

        messages.append({"role": "user", "content": user_content})
        return messages

    @staticmethod
    def _sse_bytes(content: str) -> bytes:
        """Wrap a content string as a minimal SSE data line (for synthetic responses)."""
        chunk = {"choices": [{"delta": {"content": content}, "finish_reason": None}]}
        return f"data: {json.dumps(chunk)}\n\n".encode()

    async def _stream_gateway(
        self,
        req: ChatRequest,
        uploaded_file_paths: list[str] | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """Open a streaming connection to the OpenClaw Gateway and yield SSE chunks.

        If the agent has Garage Feed connected, a non-streaming probe is made first
        to detect tool_calls. Tools are executed and then the final answer is streamed.
        """
        user_field = self._build_user_field(
            req.agent_id, req.user_id,
            session_id=req.session_id, room_id=req.room_id,
        )
        messages = self._build_messages(req, uploaded_file_paths=uploaded_file_paths)

        headers = {
            "Content-Type": "application/json",
            "x-openclaw-agent-id": req.agent_id,
        }
        if settings.OPENCLAW_GATEWAY_TOKEN:
            headers["Authorization"] = f"Bearer {settings.OPENCLAW_GATEWAY_TOKEN}"

        # ── Tool-enabled path ──────────────────────────────────────────────────
        garage_creds = await load_garage_credentials(req.agent_id)
        if garage_creds:
            probe_body = {
                "model": f"openclaw:{req.agent_id}",
                "messages": messages,
                "stream": False,
                "user": user_field,
                "tools": GARAGE_TOOLS,
            }
            async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as client:
                try:
                    probe_resp = await client.post(
                        f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                        json=probe_body,
                        headers=headers,
                    )
                except httpx.ConnectError as exc:
                    logger.error("Cannot connect to OpenClaw Gateway: %s", exc)
                    raise HTTPException(
                        status_code=502,
                        detail={
                            "error": "gateway_connection_error",
                            "message": "Cannot connect to OpenClaw Gateway",
                            "gateway_url": settings.OPENCLAW_GATEWAY_URL,
                            "hint": "Is the OpenClaw gateway running?",
                            "original_error": str(exc),
                        },
                    )

            if probe_resp.status_code == 200:
                data = probe_resp.json()
                choice = data.get("choices", [{}])[0]

                if choice.get("finish_reason") == "tool_calls":
                    # Execute all tool calls
                    assistant_msg = choice.get("message", {})
                    tool_calls = assistant_msg.get("tool_calls", [])
                    tool_results: list[dict] = []
                    for tc in tool_calls:
                        fn_name = tc.get("function", {}).get("name")
                        if fn_name == "create_garage_post":
                            try:
                                args = json.loads(tc["function"]["arguments"])
                                result = await execute_create_garage_post(
                                    req.agent_id, args.get("content", "")
                                )
                            except Exception as exc:
                                result = f"Tool execution error: {exc}"
                            tool_results.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result,
                            })

                    # Stream the final answer with tool results in context
                    follow_up_messages = messages + [assistant_msg] + tool_results
                    stream_body = {
                        "model": f"openclaw:{req.agent_id}",
                        "messages": follow_up_messages,
                        "stream": True,
                        "user": user_field,
                    }
                    async with httpx.AsyncClient(timeout=_HTTPX_STREAM_TIMEOUT) as client:
                        try:
                            async with client.stream(
                                "POST",
                                f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                                json=stream_body,
                                headers=headers,
                            ) as resp:
                                if resp.status_code != 200:
                                    err = await resp.aread()
                                    raise HTTPException(
                                        status_code=resp.status_code,
                                        detail=err.decode()[:500],
                                    )
                                async for chunk in resp.aiter_bytes():
                                    yield chunk
                        except httpx.ConnectError as exc:
                            raise HTTPException(status_code=502, detail=str(exc))
                    return

                else:
                    # Model answered directly (no tool call) — emit as synthetic SSE
                    content = choice.get("message", {}).get("content") or ""
                    yield self._sse_bytes(content)
                    yield b"data: [DONE]\n\n"
                    return

        # ── Pure streaming passthrough (no tools configured) ──────────────────
        body = {
            "model": f"openclaw:{req.agent_id}",
            "messages": messages,
            "stream": True,
            "user": user_field,
        }
        async with httpx.AsyncClient(timeout=_HTTPX_STREAM_TIMEOUT) as client:
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

    async def chat_stream(
        self,
        req: ChatRequest,
        uploaded_file_paths: list[str] | None = None,
    ) -> StreamingResponse:
        """Return a streaming SSE response proxied from the gateway."""
        return StreamingResponse(
            self._stream_gateway(req, uploaded_file_paths=uploaded_file_paths),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    async def chat_non_stream(
        self,
        req: ChatRequest,
        uploaded_file_paths: list[str] | None = None,
    ) -> dict:
        """Send a non-streaming chat request and return the full response."""
        user_field = self._build_user_field(
            req.agent_id, req.user_id,
            session_id=req.session_id, room_id=req.room_id,
        )
        messages = self._build_messages(req, uploaded_file_paths=uploaded_file_paths)

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

    def new_session(self) -> NewSessionResponse:
        """Generate a timestamp-based session ID."""
        return NewSessionResponse(session_id=str(int(time.time())))