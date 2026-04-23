"""Chat proxy — streams requests to the OpenClaw Gateway."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator

import httpx
from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..clients.wallet_client import WalletClient, InsufficientBalanceError, get_wallet_client
from ..config import settings
from ..database import SessionLocal
from ..tools.garage_tool import GARAGE_TOOLS, execute_create_garage_post, execute_deliver_chat_message
from ..services import embed_service, manual_context_service
from ..services.context_injection_service import build_context_block as build_third_party_context_block
from ..services.secret_service import SecretService
from ..services.usage_service import UsageService
from ..schemas.chat import ChatRequest, NewSessionResponse
from ..repositories.subscription_repository import SubscriptionRepository

logger = logging.getLogger("agent_manager.services.chat_service")


async def _sync_usage_after_delay(agent_id: str, session_key: str, user_id: str) -> None:
    """Wait for OpenClaw to flush its local disk write, then sync to DB and deduct wallet."""
    await asyncio.sleep(2.0)
    try:
        # Note: we use a new sync Session for the background task
        with SessionLocal() as db:
            usage_service = UsageService(gateway=None, db=db)  # type: ignore
            await usage_service.sync_single_session(agent_id, session_key, user_id)
            # Deduct cost from wallet after syncing
            await usage_service.deduct_session_cost(user_id, session_key)
    except Exception as exc:
        logger.error("Failed to background sync usage for %s: %s", session_key, exc)


# Timeout for non-streaming requests (sync completions).
_HTTPX_TIMEOUT = httpx.Timeout(connect=10.0, read=3000.0, write=10.0, pool=10.0)

# For streaming: no read timeout — reasoning models may think silently for
# several minutes before emitting the first token.
_HTTPX_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)


# Retry delays for transient openclaw-gateway unavailability. The gateway
# reloads its Node process whenever its config is patched — notably after
# every agent create/update via agent_service.patch_config, and on
# installer/config-watch events. That creates a ~10 second window where
# incoming chat requests see ``ConnectError`` before the gateway is ready.
# Sum of delays here bridges a single cold boot transparently. We only
# retry ``ConnectError`` — other exceptions bubble immediately.
_GATEWAY_RETRY_DELAYS_S = (0.5, 1.0, 2.0, 4.0)


async def _post_with_gateway_retry(client: httpx.AsyncClient, url: str, **kwargs):
    """POST that retries on ``ConnectError`` to absorb gateway restarts.

    See ``_GATEWAY_RETRY_DELAYS_S`` for the backoff schedule. After the
    schedule is exhausted, re-raises the last ``ConnectError``.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate((0.0, *_GATEWAY_RETRY_DELAYS_S)):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await client.post(url, **kwargs)
        except httpx.ConnectError as exc:
            last_exc = exc
            logger.warning(
                "OpenClaw gateway ConnectError on attempt %d (%s); will retry",
                attempt + 1, exc,
            )
    assert last_exc is not None
    raise last_exc


async def _wait_for_gateway_ready() -> None:
    """Poll the gateway's dashboard root until it answers, then return.

    Used before opening a streaming ``client.stream`` — httpx's stream
    entry raises ConnectError for cold gateways, and retrying around
    ``async with client.stream(...)`` is awkward. A fast readiness probe
    on the same loopback address is simpler: it succeeds in ~1ms when
    the gateway is up and retries transparently while it's still booting.

    No-op (returns) on the first success. Raises ``HTTPException(502)``
    after the retry schedule is exhausted.
    """
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        for attempt, delay in enumerate((0.0, *_GATEWAY_RETRY_DELAYS_S)):
            if delay:
                await asyncio.sleep(delay)
            try:
                # The dashboard root (``/``) is always served and cheap.
                # We don't care about the status code, only that the TCP
                # connection succeeds — a 200/404/405 all mean "up".
                await client.get(settings.OPENCLAW_GATEWAY_URL + "/")
                return
            except httpx.ConnectError as exc:
                last_exc = exc
                logger.warning(
                    "Gateway readiness probe failed on attempt %d (%s); will retry",
                    attempt + 1, exc,
                )
    raise HTTPException(
        status_code=502,
        detail={
            "error": "gateway_connection_error",
            "message": "OpenClaw gateway did not become ready",
            "gateway_url": settings.OPENCLAW_GATEWAY_URL,
            "original_error": str(last_exc) if last_exc else "unknown",
        },
    )


async def _check_wallet_balance(user_id: str, agent_id: str = "") -> None:
    """Pre-flight balance + debt check. Raises HTTPException 402 if blocked."""
    if not settings.WALLET_INTERNAL_API_KEY and not settings.GARAGE_WALLET_INTERNAL_API_KEY:
        return  # Wallet integration not configured, skip check

    try:
        wallet = get_wallet_client(agent_id)
        result = await wallet.check_balance(user_id)
        # Wallet returns balanceCents/debtCents at top level (not nested under "data")
        balance_cents = result.get("balanceCents", result.get("data", {}).get("balanceCents", 0))
        debt_cents = result.get("debtCents", result.get("data", {}).get("debtCents", 0))

        # Block if debt has hit the cap ($2)
        if debt_cents >= settings.MAX_DEBT_CENTS:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "debt_limit_reached",
                    "message": (
                        f"Debt limit reached (${debt_cents / 100:.2f}/${settings.MAX_DEBT_CENTS / 100:.2f}). "
                        "Please add credits to clear your debt and continue."
                    ),
                    "balanceCents": balance_cents,
                    "debtCents": debt_cents,
                    "maxDebtCents": settings.MAX_DEBT_CENTS,
                },
            )

        # Block if no balance and already in debt
        if balance_cents < settings.MIN_BALANCE_CENTS and debt_cents > 0:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_balance",
                    "message": (
                        f"Insufficient balance (${balance_cents / 100:.2f}) with outstanding debt "
                        f"(${debt_cents / 100:.2f}). Please add credits."
                    ),
                    "balanceCents": balance_cents,
                    "debtCents": debt_cents,
                },
            )

        # Block if balance is zero (no debt yet)
        if balance_cents < settings.MIN_BALANCE_CENTS:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "insufficient_balance",
                    "message": "Insufficient wallet balance to use agents. Please add credits.",
                    "balanceCents": balance_cents,
                    "balanceDollars": f"{balance_cents / 100:.2f}",
                    "minBalanceCents": settings.MIN_BALANCE_CENTS,
                },
            )
    except HTTPException:
        raise
    except Exception as exc:
        # Wallet service unreachable — allow request to proceed (graceful degradation)
        logger.warning("Wallet pre-flight check failed (allowing request): %s", exc)


def _check_agent_subscription(agent_id: str, db: Session | None) -> None:
    """Block chat if agent subscription is locked or deleted.

    No-op when ``settings.ENFORCE_AGENT_SUBSCRIPTION`` is False — in that
    mode we only charge pay-as-you-go via the wallet balance check, and
    the monthly $24 agent lock is not enforced. Flip the flag to re-enable.
    The ``deleted`` state is still honored regardless because soft-deleted
    agents should not be usable no matter which billing model is active.
    """
    if not db:
        return
    sub_repo = SubscriptionRepository(db)
    sub = sub_repo.get_by_agent_id(agent_id)
    if not sub:
        return  # Legacy agent without subscription
    if sub.status == "deleted":
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    if not settings.ENFORCE_AGENT_SUBSCRIPTION:
        return  # Subscription enforcement disabled — pay-as-you-go only
    if sub.status == "locked":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "agent_locked",
                "message": "Agent is locked due to unpaid subscription. Please add credits to unlock.",
            },
        )


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
        """Build the messages list, injecting recent_context and session metadata."""
        messages = [{"role": m.role, "content": m.content} for m in req.history]

        # Always include a system-level session descriptor so the agent can
        # reliably know who it's talking to and which session to use for
        # downstream tools/logging.
        session_meta_lines = [
            "[SESSION METADATA]",
            f"user_id: {req.user_id}",
            f"session_id: {req.session_id or ''}",
        ]
        if req.room_id:
            session_meta_lines.append(f"room_id: {req.room_id}")
        session_meta = "\n".join(session_meta_lines)
        messages.insert(0, {"role": "system", "content": session_meta})

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
    
    def _log_chat_error(
        self,
        db: Session | None,
        agent_id: str,
        user_id: str | None,
        error_type: str,
        summary: str,
        metadata: dict | None = None,
    ) -> None:
        """Persist a chat/LLM error to the activity stream so founders and
        employees can see it in the activity feed — live for the
        affected user via WS, and in history for everyone who reads the
        feed later. Critical for diagnosing cron-job failures: a cron
        running overnight that hits a provider rate limit will surface
        the error here, explaining the cron's downstream failure."""
        if db is None:
            return
        try:
            from .agent_activity_service import log_activity_sync
            log_activity_sync(
                db, agent_id, error_type, summary,
                metadata=metadata or {},
                status="error",
                user_id=user_id,
            )
        except Exception:
            # Never let logging-the-error shadow the real error.
            logger.exception("failed to log chat error to activity stream")

    def _raise_for_status(
        self,
        status_code: int,
        body: str,
        agent_id: str,
        db: Session | None = None,
        user_id: str | None = None,
    ) -> None:
        """Raise appropriate HTTPException based on gateway status code."""
        if status_code == 429:
            # Try to extract retry-after from body if gateway forwards it
            retry_after = None
            try:
                data = json.loads(body)
                retry_after = (
                    data.get("retry_after")
                    or data.get("error", {}).get("retry_after")
                )
            except (json.JSONDecodeError, AttributeError):
                pass

            detail = {
                "error": "rate_limit_exceeded",
                "message": "OpenClaw Gateway rate limit reached. Please slow down.",
                "agent_id": agent_id,
                "gateway_response": body[:500],
            }
            if retry_after:
                detail["retry_after_seconds"] = retry_after

            logger.warning("Rate limit hit for agent %s: %s", agent_id, body[:200])
            self._log_chat_error(
                db, agent_id, user_id,
                "llm_rate_limit",
                "LLM rate limit hit" + (f" (retry after {retry_after}s)" if retry_after else ""),
                metadata={"status_code": 429, "body_preview": body[:200], "retry_after": retry_after},
            )
            raise HTTPException(status_code=429, detail=detail)

        if status_code == 500:
            # OpenClaw masks upstream 429s as 500 "internal error"
            is_masked_rate_limit = False
            try:
                data = json.loads(body)
                msg = (data.get("error", {}).get("message") or "").lower()
                if msg in ("internal error", "internal_error", ""):
                    is_masked_rate_limit = True
            except (json.JSONDecodeError, AttributeError):
                pass

            if is_masked_rate_limit:
                logger.warning(
                    "Suspected masked rate limit (500 internal error) for agent %s: %s",
                    agent_id, body[:200],
                )
                self._log_chat_error(
                    db, agent_id, user_id,
                    "llm_rate_limit",
                    "LLM rate limit (masked as 500 by gateway)",
                    metadata={"status_code": 500, "body_preview": body[:200]},
                )
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": "LLM provider rate limit likely hit (gateway returned 500 internal error).",
                        "agent_id": agent_id,
                        "gateway_response": body[:500],
                        "hint": "OpenClaw is masking the upstream 429 as a 500.",
                    },
                )

        if status_code != 200:
            self._log_chat_error(
                db, agent_id, user_id,
                "llm_error",
                f"Gateway returned HTTP {status_code}",
                metadata={"status_code": status_code, "body_preview": body[:200]},
            )
            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": "gateway_upstream_error",
                    "message": f"OpenClaw Gateway returned HTTP {status_code}",
                    "gateway_url": f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                    "agent_id": agent_id,
                    "gateway_response": body[:500],
                },
            )

    @staticmethod
    def _sse_bytes(content: str) -> bytes:
        """Wrap a content string as a minimal SSE data line (for synthetic responses)."""
        chunk = {"choices": [{"delta": {"content": content}, "finish_reason": None}]}
        return f"data: {json.dumps(chunk)}\n\n".encode()

    async def _stream_gateway(
        self,
        req: ChatRequest,
        uploaded_file_paths: list[str] | None = None,
        db: Session | None = None,
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

        # ── Shared query embedding for both auto-inject paths ─────────
        # Manual context and third-party context both embed the same
        # ``req.message`` to run their semantic searches. Compute the
        # vector at most once per chat turn and share it between both
        # builders. The closure defers the actual compute until one
        # of them needs it — agents with neither manual contexts nor
        # third-party integrations assigned pay zero embedding cost.
        _embed_cache: dict[str, list[float]] = {}

        async def _get_query_vector() -> list[float] | None:
            if "v" in _embed_cache:
                return _embed_cache["v"]
            try:
                loop = asyncio.get_running_loop()
                vec = await loop.run_in_executor(
                    None, embed_service.embed_single, req.message
                )
                _embed_cache["v"] = vec
                return vec
            except Exception:
                logger.exception(
                    "Query embedding failed for auto-inject (agent=%s)",
                    req.agent_id,
                )
                return None

        # ── Auto-inject manual context ────────────────────────────────
        # Top-3 chunks from the agent's assigned knowledge documents,
        # relevance-gated and char-capped. See
        # ``manual_context_service.build_auto_inject_block``.
        if db:
            try:
                vec = await _get_query_vector()
                ctx_block = manual_context_service.build_auto_inject_block(
                    db, req.agent_id, req.message, query_vector=vec
                )
                if ctx_block:
                    messages.insert(1, {"role": "system", "content": ctx_block})
            except Exception as exc:
                logger.warning(
                    "Manual context auto-inject failed for agent %s: %s",
                    req.agent_id,
                    exc,
                )

        # ── Auto-inject third-party context ───────────────────────────
        # Top-3 chunks from the agent's connected integrations (Gmail,
        # Drive, Notion, Slack, etc.), also relevance-gated and
        # char-capped. Unified single-query implementation (no more
        # per-source parallel queries) so the cost is constant
        # regardless of how many integrations are connected. See
        # ``context_injection_service.build_context_block``.
        #
        # Insertion order matters: since both blocks insert at index 1,
        # the block inserted LATER shifts the earlier one down. With
        # manual first then third-party second, the final message
        # layout is:
        #   [0] main system prompt
        #   [1] third-party context block
        #   [2] manual context block
        #   [3+] conversation history
        # Manual ends up CLOSER to the user message than third-party.
        # That's deliberate — manual contexts are user-curated and
        # higher-signal than third-party snippets (which include noisy
        # email threads and random document excerpts), so putting
        # manual closer to the user turn gives it more attention from
        # the model.
        if db:
            try:
                vec = await _get_query_vector()
                tp_block = await build_third_party_context_block(
                    db, req.agent_id, req.message, query_vector=vec
                )
                if tp_block:
                    messages.insert(1, {"role": "system", "content": tp_block})
            except Exception as exc:
                logger.warning(
                    "Third-party context auto-inject failed for agent %s: %s",
                    req.agent_id,
                    exc,
                )

        headers = {
            "Content-Type": "application/json",
            "x-openclaw-agent-id": req.agent_id,
        }
        if settings.OPENCLAW_GATEWAY_TOKEN:
            headers["Authorization"] = f"Bearer {settings.OPENCLAW_GATEWAY_TOKEN}"

        # LLM model override. Priority:
        #   1. ``req.model`` — per-turn override from the chat UI picker.
        #   2. ``agent_registry.llm_model`` — agent's locked default.
        #   3. gateway's configured primary (no header sent).
        # Both forms are validated against the same allowlist; the
        # gateway enforces the allowlist too. Same header the voice
        # bridge uses.
        chosen_model: str | None = None
        if getattr(req, "model", None):
            chosen_model = req.model
        elif db:
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            agent_row = AgentRegistryRepository(db).get(req.agent_id)
            if agent_row and agent_row.llm_model:
                chosen_model = agent_row.llm_model
        if chosen_model:
            headers["x-openclaw-model"] = chosen_model

        # ── Tool-enabled path ──────────────────────────────────────────────────
        # Always include deliver_chat_message; only include create_garage_post if creds exist
        garage_creds = SecretService.get_secret(db, req.agent_id, "garage_feed") if db else None
        active_tools = [t for t in GARAGE_TOOLS if t["function"]["name"] != "create_garage_post" or garage_creds]
        if active_tools:
            probe_body = {
                "model": f"openclaw:{req.agent_id}",
                "messages": messages,
                "stream": False,
                "user": user_field,
                "tools": active_tools,
            }
            async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as client:
                try:
                    probe_resp = await _post_with_gateway_retry(
                        client,
                        f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                        json=probe_body,
                        headers=headers,
                    )
                except httpx.ConnectError as exc:
                    logger.error("Cannot connect to OpenClaw Gateway after retries: %s", exc)
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
                        result = None
                        if fn_name == "create_garage_post":
                            try:
                                args = json.loads(tc["function"]["arguments"])
                                result = await execute_create_garage_post(
                                    req.agent_id,
                                    args.get("content", ""),
                                    args.get("channelIds") or None,
                                )
                            except Exception as exc:
                                result = f"Tool execution error: {exc}"
                        elif fn_name == "deliver_chat_message":
                            try:
                                args = json.loads(tc["function"]["arguments"])
                                result = await execute_deliver_chat_message(
                                    agent_id=req.agent_id,
                                    user_id=req.user_id,
                                    session_id=req.session_id or "",
                                    content=args.get("content", ""),
                                )
                            except Exception as exc:
                                result = f"Tool execution error: {exc}"
                        if result is not None:
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
                    # Wait for gateway readiness before streaming — absorbs
                    # the ~10s cold-boot window after create_agent patches
                    # the config. See _wait_for_gateway_ready.
                    await _wait_for_gateway_ready()
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
                                    self._raise_for_status(resp.status_code, err.decode(), req.agent_id, db=db, user_id=req.user_id)
                                received_content = False
                                async for chunk in resp.aiter_bytes():
                                    if chunk:
                                        decoded = chunk.decode(errors="ignore")
                                        if "data: [DONE]" in decoded and not received_content:
                                            logger.warning(
                                                "Empty stream (premature DONE) for agent %s — likely masked rate limit",
                                                req.agent_id,
                                            )
                                            error_chunk = {
                                                "error": "rate_limit_exceeded",
                                                "message": "LLM provider rate limit likely hit (empty stream response).",
                                                "agent_id": req.agent_id,
                                                "hint": "Gateway returned [DONE] immediately with no content.",
                                            }
                                            yield f"data: {json.dumps(error_chunk)}\n\n".encode()
                                            return
                                        if '"delta"' in decoded and '"content"' in decoded:
                                            received_content = True
                                        yield chunk
                                # Stream ended — check if we got nothing at all
                                if not received_content:
                                    logger.warning(
                                        "Empty stream (no content chunks) for agent %s — likely masked rate limit",
                                        req.agent_id,
                                    )
                                    error_chunk = {
                                        "error": "rate_limit_exceeded",
                                        "message": "LLM provider rate limit likely hit (empty stream response).",
                                        "agent_id": req.agent_id,
                                        "hint": "Gateway returned an empty stream with no content.",
                                    }
                                    yield f"data: {json.dumps(error_chunk)}\n\n".encode()
                                    return
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
        # Readiness probe — same rationale as the tool-enabled path above.
        await _wait_for_gateway_ready()
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
                        self._raise_for_status(resp.status_code, error_body.decode(), req.agent_id, db=db, user_id=req.user_id)

                    received_content = False
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            decoded = chunk.decode(errors="ignore")
                            if "data: [DONE]" in decoded and not received_content:
                                logger.warning(
                                    "Empty stream (premature DONE) for agent %s — likely masked rate limit",
                                    req.agent_id,
                                )
                                error_chunk = {
                                    "error": "rate_limit_exceeded",
                                    "message": "LLM provider rate limit likely hit (empty stream response).",
                                    "agent_id": req.agent_id,
                                    "hint": "Gateway returned [DONE] immediately with no content.",
                                }
                                yield f"data: {json.dumps(error_chunk)}\n\n".encode()
                                return
                            if '"delta"' in decoded and '"content"' in decoded:
                                received_content = True
                            yield chunk
                    # Stream ended — check if we got nothing at all
                    if not received_content:
                        logger.warning(
                            "Empty stream (no content chunks) for agent %s — likely masked rate limit",
                            req.agent_id,
                        )
                        error_chunk = {
                            "error": "rate_limit_exceeded",
                            "message": "LLM provider rate limit likely hit (empty stream response).",
                            "agent_id": req.agent_id,
                            "hint": "Gateway returned an empty stream with no content.",
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n".encode()
                        return
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
        db: Session | None = None,
    ) -> StreamingResponse:
        """Return a streaming SSE response proxied from the gateway."""
        _check_agent_subscription(req.agent_id, db)
        await _check_wallet_balance(req.user_id, req.agent_id)

        user_field = self._build_user_field(
            req.agent_id, req.user_id,
            session_id=req.session_id, room_id=req.room_id,
        )
        bg_task = BackgroundTasks()
        session_key = f"agent:{req.agent_id}:openai-user:{user_field}"
        bg_task.add_task(_sync_usage_after_delay, req.agent_id, session_key, req.user_id)

        # Intentionally no chat_message_received/chat_response_sent activity
        # log here — full transcripts live in chat history already. Errors
        # (rate limits, gateway failures) still surface via _raise_for_status
        # → _log_chat_error so operators can spot them in the activity feed.
        return StreamingResponse(
            self._stream_gateway(req, uploaded_file_paths=uploaded_file_paths, db=db),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
            background=bg_task,
        )

    async def chat_non_stream(
        self,
        req: ChatRequest,
        background_tasks: BackgroundTasks,
        uploaded_file_paths: list[str] | None = None,
        db: Session | None = None,
    ) -> dict:
        """Send a non-streaming chat request and return the full response."""
        _check_agent_subscription(req.agent_id, db)
        await _check_wallet_balance(req.user_id, req.agent_id)

        user_field = self._build_user_field(
            req.agent_id, req.user_id,
            session_id=req.session_id, room_id=req.room_id,
        )

        session_key = f"agent:{req.agent_id}:openai-user:{user_field}"
        background_tasks.add_task(_sync_usage_after_delay, req.agent_id, session_key, req.user_id)

        messages = self._build_messages(req, uploaded_file_paths=uploaded_file_paths)

        # Auto-inject manual + third-party context — same hybrid RAG
        # path as _stream_gateway. See that function for the rationale,
        # insertion-order comments, and shared-embedding design. Both
        # paths share one embedding via the local cache closure.
        _embed_cache2: dict[str, list[float]] = {}

        async def _get_query_vector2() -> list[float] | None:
            if "v" in _embed_cache2:
                return _embed_cache2["v"]
            try:
                loop = asyncio.get_running_loop()
                vec = await loop.run_in_executor(
                    None, embed_service.embed_single, req.message
                )
                _embed_cache2["v"] = vec
                return vec
            except Exception:
                logger.exception(
                    "Query embedding failed for auto-inject (agent=%s)",
                    req.agent_id,
                )
                return None

        if db:
            try:
                vec = await _get_query_vector2()
                ctx_block = manual_context_service.build_auto_inject_block(
                    db, req.agent_id, req.message, query_vector=vec
                )
                if ctx_block:
                    messages.insert(1, {"role": "system", "content": ctx_block})
            except Exception as exc:
                logger.warning(
                    "Manual context auto-inject failed for agent %s: %s",
                    req.agent_id,
                    exc,
                )
            try:
                vec = await _get_query_vector2()
                tp_block = await build_third_party_context_block(
                    db, req.agent_id, req.message, query_vector=vec
                )
                if tp_block:
                    messages.insert(1, {"role": "system", "content": tp_block})
            except Exception as exc:
                logger.warning(
                    "Third-party context auto-inject failed for agent %s: %s",
                    req.agent_id,
                    exc,
                )

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

        # LLM model override — see comment in chat_stream's headers block.
        # Priority: req.model (per-turn) > agent.llm_model (default) > gateway primary.
        chosen_model: str | None = None
        if getattr(req, "model", None):
            chosen_model = req.model
        elif db:
            from ..repositories.agent_registry_repository import AgentRegistryRepository
            agent_row = AgentRegistryRepository(db).get(req.agent_id)
            if agent_row and agent_row.llm_model:
                chosen_model = agent_row.llm_model
        if chosen_model:
            headers["x-openclaw-model"] = chosen_model

        async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as client:
            try:
                resp = await _post_with_gateway_retry(
                    client,
                    f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions",
                    json=body,
                    headers=headers,
                )
                if resp.status_code != 200:
                    self._raise_for_status(resp.status_code, resp.text, req.agent_id, db=db, user_id=req.user_id)
                data = resp.json()
                content = ""
                if "choices" in data and data["choices"]:
                    choice = data["choices"][0]
                    message = choice.get("message", {})
                    content = message.get("content", "")

                # No success-path activity log here — same rationale as
                # chat_stream. Errors are handled by _raise_for_status +
                # the except blocks below.
                return {"response": content, "raw": data}
            except httpx.ConnectError as exc:
                self._log_chat_error(
                    db, req.agent_id, req.user_id,
                    "llm_gateway_unreachable",
                    "LLM gateway unreachable",
                    metadata={"gateway_url": settings.OPENCLAW_GATEWAY_URL, "original_error": str(exc)[:200]},
                )
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