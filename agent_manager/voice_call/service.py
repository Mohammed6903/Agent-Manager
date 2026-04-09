"""VoiceCallService — orchestrates the outbound call lifecycle.

Multi-worker safe for voxtral mode. Webhook handlers and the
``initiate_outbound`` method use Redis-backed cross-worker state
(:mod:`call_state_store`) so any gunicorn worker can serve any event for
any call. The in-memory ``local_call_runtime`` is only consulted by the
WebSocket handler on the worker that owns the audio loop.

Responsibilities:
- Persist VoiceCall records (start, update state, finalize)
- Call Telnyx to dial and to start media streaming
- Seed Redis with call state so webhooks landing on any worker can resolve it
- Handle Telnyx webhook events (call.initiated, call.answered, call.hangup, ...)
- Expose list/get endpoints for introspection
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models.voice_call import VoiceCall, VoiceCallTurn
from . import call_state_store
from .agent_bridge import VoiceAgentSession, run_agent_turn
from .schemas import CallView, InitiateCallRequest, InitiateCallResponse, TurnView
from .state_machine import CallRuntime, local_call_runtime
from .telnyx_client import TelnyxClient, TelnyxError

logger = logging.getLogger(__name__)

DEFAULT_GREETING = "Hi! This is your AI agent. How can I help you today?"


class VoiceCallService:
    def __init__(self, db: Session, telnyx: Optional[TelnyxClient] = None):
        self.db = db
        self.telnyx = telnyx or TelnyxClient()

    # ── Outbound initiation ──────────────────────────────────────────────

    # Active call states — anything not in this set is considered terminal
    # and a fresh call to the same number is OK.
    _ACTIVE_STATES = {
        "initiated",
        "ringing",
        "answered",
        "speaking",
        "listening",
    }
    # How recent an "in flight" call must be to count as a duplicate. Older
    # records that never got finalized (e.g., crashed mid-call) shouldn't
    # block a new attempt forever.
    _DEDUP_WINDOW_MINUTES = 5

    def _find_active_call_to(
        self, *, to_number: str, agent_id: Optional[str]
    ) -> Optional[VoiceCall]:
        """Look for an in-flight call to the same number for the same agent.

        Returns the most recent active call or None. The agent calling
        ``make_phone_call`` twice for the same number (which has been
        observed in production when the model panics over slow webhooks)
        should NOT result in two phones ringing.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self._DEDUP_WINDOW_MINUTES)
        q = (
            self.db.query(VoiceCall)
            .filter(VoiceCall.to_number == to_number)
            .filter(VoiceCall.started_at >= cutoff)
            .filter(VoiceCall.state.in_(list(self._ACTIVE_STATES)))
        )
        if agent_id:
            q = q.filter(VoiceCall.agent_id == agent_id)
        return q.order_by(VoiceCall.started_at.desc()).first()

    async def initiate_outbound(
        self, req: InitiateCallRequest
    ) -> InitiateCallResponse:
        if not settings.VOICE_CALL_PUBLIC_URL:
            raise RuntimeError(
                "VOICE_CALL_PUBLIC_URL not configured — Telnyx cannot reach the webhook"
            )

        # ── Dedup: if there's already a live call to this number for this
        # agent, return that one instead of dialing a second phone. This
        # protects against the agent calling the tool repeatedly while the
        # first call is still being placed (LLMs sometimes retry tool
        # invocations when they don't trust the result).
        existing = self._find_active_call_to(
            to_number=req.to, agent_id=req.agent_id
        )
        if existing is not None:
            logger.info(
                "Outbound call dedup: returning existing %s (state=%s) for %s",
                existing.id,
                existing.state,
                req.to,
            )
            return InitiateCallResponse(
                call_id=str(existing.id),
                telnyx_call_control_id=existing.telnyx_call_control_id,
                state=existing.state,
                from_number=existing.from_number,
                to_number=existing.to_number,
                started_at=existing.started_at,
                deduped=True,
                message=(
                    f"A call to {req.to} is already in progress (state: "
                    f"{existing.state}). Did NOT place a duplicate call. "
                    f"Use get_voice_call(call_id='{existing.id}') to check "
                    f"its status. Tell the user the call is already being "
                    f"delivered."
                ),
            )

        greeting = (req.initial_message or DEFAULT_GREETING).strip()

        # Persist a placeholder row first so we have a call_id before Telnyx.
        call_id = uuid.uuid4()
        record = VoiceCall(
            id=call_id,
            direction="outbound",
            state="initiated",
            from_number=self.telnyx.from_number,
            to_number=req.to,
            user_id=req.user_id,
            agent_id=req.agent_id,
            initial_message=greeting,
            agent_context=req.agent_context,
            started_at=datetime.now(timezone.utc),
            meta={},
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        call_id_str = str(record.id)
        use_voxtral = settings.VOICE_CALL_USE_VOXTRAL

        # Seed Redis BEFORE calling Telnyx so any worker that receives
        # the resulting webhooks can find the call's state. We do NOT
        # create a local CallRuntime here — that gets created on whichever
        # worker the media-stream WebSocket lands on, which may be a
        # different worker than this one.
        call_state_store.create(
            call_id=call_id_str,
            direction="outbound",
            use_voxtral=use_voxtral,
            agent_id=req.agent_id,
            initial_message=greeting,
            system_prompt=req.system_prompt,
        )

        logger.info(
            "Outbound call %s → %s (mode=%s, pid=%s)",
            call_id_str,
            req.to,
            "voxtral" if use_voxtral else "telnyx-only",
            __import__("os").getpid(),
        )

        webhook_url = settings.VOICE_CALL_PUBLIC_URL.rstrip("/") + "/api/voice/webhooks/telnyx"

        try:
            data = await self.telnyx.initiate_call(
                to=req.to,
                webhook_url=webhook_url,
                client_state=call_id_str,
            )
        except TelnyxError as exc:
            # Record failure and clean up Redis state.
            record.state = "failed"
            record.failure_error = f"Telnyx API error {exc.status}: {exc.detail}"
            record.ended_at = datetime.now(timezone.utc)
            self.db.commit()
            call_state_store.delete(call_id_str)
            raise
        except Exception as exc:
            record.state = "failed"
            record.failure_error = f"{type(exc).__name__}: {exc}"
            record.ended_at = datetime.now(timezone.utc)
            self.db.commit()
            call_state_store.delete(call_id_str)
            raise

        cci = data.get("call_control_id")
        leg = data.get("call_leg_id")
        if cci:
            call_state_store.set_cci(call_id=call_id_str, cci=cci)
            record.telnyx_call_control_id = cci
        if leg:
            record.telnyx_call_leg_id = leg

        record.meta = {**(record.meta or {}), "initiate_response": data}
        self.db.commit()
        self.db.refresh(record)

        # NOTE on max-duration timer: previously we created an asyncio.Task
        # here to enforce VOICE_CALL_MAX_DURATION_SEC. With multi-worker
        # routing the WS may land on a different worker than this one, and
        # an asyncio.Task on the wrong worker can't see / cancel the right
        # call. The timer now lives inside ``handle_media_stream`` so it
        # runs on the WS owner worker. Telnyx ALSO enforces ``timeout_secs``
        # on the call API itself (we pass 30s for ringing timeout), and the
        # call.hangup webhook will fire when Telnyx tears down the call.

        return InitiateCallResponse(
            call_id=call_id_str,
            telnyx_call_control_id=cci,
            state=record.state,
            from_number=record.from_number,
            to_number=record.to_number,
            started_at=record.started_at,
            deduped=False,
            message=(
                f"Call to {record.to_number} placed successfully. The recipient's "
                f"phone is ringing now. The bot will speak the greeting when they "
                f"answer. Tell the user the call is on its way — do NOT call "
                f"make_phone_call again. Use get_voice_call(call_id='{call_id_str}') "
                f"if you need to check status later."
            ),
        )

    # ── Webhook handling ────────────────────────────────────────────────

    async def handle_webhook_event(self, payload: dict[str, Any]) -> None:
        """Dispatch one Telnyx webhook event.

        Telnyx wraps events as ``{"data": {"event_type": ..., "payload": {...}}}``.
        We extract the call_control_id and call_id (from our base64 client_state
        OR Redis lookup) and fan out by event type. Multi-worker safe — no
        access to the in-memory ``local_call_runtime`` here.
        """
        data = payload.get("data") or {}
        event_type = data.get("event_type") or ""
        inner = data.get("payload") or {}

        cci = inner.get("call_control_id")
        if not cci:
            logger.debug("Webhook without call_control_id, skipping: %s", event_type)
            return

        # Resolve our internal call_id from client_state (base64 of call_id_str).
        call_id_str: Optional[str] = None
        client_state_b64 = inner.get("client_state")
        if client_state_b64:
            try:
                import base64

                call_id_str = base64.b64decode(client_state_b64).decode("utf-8")
            except Exception:
                call_id_str = None
        if call_id_str is None:
            # Fall back to Redis cci → call_id lookup (cross-worker safe).
            call_id_str = call_state_store.get_call_id_by_cci(cci)
        if call_id_str is None:
            logger.warning(
                "Webhook for unknown call (cci=%s, event=%s)", cci, event_type
            )
            return

        # Load DB record.
        record = (
            self.db.query(VoiceCall)
            .filter(VoiceCall.id == call_id_str)
            .first()
        )
        if record is None:
            logger.warning("Webhook for missing DB row call_id=%s", call_id_str)
            return

        # Read persistent state from Redis (cross-worker safe). May be None
        # if the call has already been cleaned up.
        persistent = call_state_store.get(call_id_str)
        use_voxtral = (
            persistent.get("use_voxtral") if persistent else settings.VOICE_CALL_USE_VOXTRAL
        )

        logger.debug(
            "Telnyx webhook: event=%s call_id=%s", event_type, call_id_str
        )

        if event_type == "call.initiated":
            # Outbound leg created — we've already set state to 'initiated' on POST.
            return

        if event_type == "call.ringing":
            record.state = "ringing"
            self.db.commit()
            return

        if event_type == "call.answered":
            record.state = "answered"
            record.answered_at = datetime.now(timezone.utc)
            self.db.commit()
            if not use_voxtral:
                # Telnyx-only mode: speak the opening message via /actions/speak
                # and start server-side transcription. The conversation continues
                # via call.speak.ended → call.transcription events.
                # NOTE: Telnyx-only mode is single-worker only — its
                # _telnyx_speak_initial uses the local runtime which only
                # exists if the same worker handled both initiate and webhook.
                await self._telnyx_speak_initial_multiworker(record, persistent)
            else:
                # Voxtral mode: tell Telnyx to open the bidirectional media
                # stream. Whichever worker receives the WS upgrade becomes
                # the audio loop owner — fully multi-worker safe.
                await self._start_media_stream(record)
            return

        if event_type == "call.speak.ended":
            if not use_voxtral:
                # Telnyx-only mode: only handle if the local runtime exists
                # (single-worker fallback). In multi-worker mode, this path
                # is fragile — see Telnyx-only mode caveat in module docstring.
                runtime = local_call_runtime.get(call_id_str)
                if runtime is not None:
                    await self._telnyx_after_speak_ended(record, runtime)
            return

        if event_type == "call.transcription":
            if not use_voxtral:
                runtime = local_call_runtime.get(call_id_str)
                if runtime is not None:
                    await self._telnyx_handle_transcription(record, runtime, inner)
            return

        if event_type in ("call.hangup", "call.ended"):
            hangup_cause = inner.get("hangup_cause") or "unknown"
            record.state = "ended"
            record.end_reason = hangup_cause
            record.ended_at = datetime.now(timezone.utc)
            if record.answered_at:
                record.duration_ms = int(
                    (record.ended_at - record.answered_at).total_seconds() * 1000
                )
            self.db.commit()
            # Clean up Redis state. Local runtime (if any) is on the WS owner
            # worker — Telnyx will close the WebSocket and that worker will
            # clean up its local state on disconnect.
            call_state_store.delete(call_id_str)
            return

        if event_type == "streaming.started":
            # Informational — the media WS endpoint will already be doing its thing.
            return

        if event_type == "streaming.failed":
            reason = inner.get("failure_reason") or "streaming failure"
            logger.warning(
                "Telnyx streaming failed for call %s: %s", call_id_str, reason
            )
            record.failure_error = reason
            self.db.commit()
            return

        logger.debug(
            "Unhandled Telnyx event type %s for call %s", event_type, call_id_str
        )

    async def _start_media_stream(self, record: VoiceCall) -> None:
        """Tell Telnyx to open the media stream WebSocket to our endpoint."""
        cci = record.telnyx_call_control_id
        if not cci:
            logger.warning(
                "Cannot start media stream for call %s: no call_control_id",
                record.id,
            )
            return
        if not settings.VOICE_CALL_PUBLIC_URL:
            logger.error(
                "VOICE_CALL_PUBLIC_URL not configured — cannot derive wss URL"
            )
            return

        # Public URL is https://...; Telnyx media stream needs wss://...
        public = settings.VOICE_CALL_PUBLIC_URL.rstrip("/")
        if public.startswith("https://"):
            ws_base = "wss://" + public[len("https://") :]
        elif public.startswith("http://"):
            ws_base = "ws://" + public[len("http://") :]
        else:
            ws_base = public
        stream_url = f"{ws_base}/api/voice/stream/{record.id}"

        try:
            await self.telnyx.streaming_start(
                call_control_id=cci,
                stream_url=stream_url,
            )
        except TelnyxError as exc:
            logger.error(
                "Failed to start Telnyx media stream for call %s: %s",
                record.id,
                exc,
            )
            record.failure_error = f"streaming_start failed: {exc.detail}"
            self.db.commit()

    # ── Telnyx-only mode (server-side TTS + STT) ─────────────────────────

    async def _telnyx_speak_initial_multiworker(
        self, record: VoiceCall, persistent: Optional[dict[str, Any]]
    ) -> None:
        """Multi-worker safe version of speaking the initial message.

        For Telnyx-only mode, the call.answered webhook may land on a worker
        that has no local CallRuntime. We can still speak the initial message
        because that just requires an HTTP call to Telnyx — no in-memory state.

        Subsequent conversation turns DO need state coordination, which is
        only safe if all webhook events for the call land on the same
        worker — currently not enforced. See module docstring for the
        Telnyx-only mode caveat.
        """
        cci = record.telnyx_call_control_id
        if not cci or not record.initial_message:
            return
        try:
            await self.telnyx.speak(
                call_control_id=cci,
                text=record.initial_message,
                voice=settings.VOICE_CALL_TELNYX_TTS_VOICE,
                language=settings.VOICE_CALL_TELNYX_TTS_LANGUAGE,
            )
            _persist_turn_sync(str(record.id), speaker="bot", text=record.initial_message)
            logger.debug("Telnyx mode: spoke initial message for call %s", record.id)
            call_state_store.update(str(record.id), {"telnyx_phase": "speaking"})
        except Exception:
            logger.exception(
                "Telnyx speak (initial) failed for call %s", record.id
            )
            call_state_store.update(str(record.id), {"telnyx_phase": "idle"})

    async def _telnyx_speak_initial(
        self, record: VoiceCall, runtime: CallRuntime
    ) -> None:
        """Speak the opening message via Telnyx Polly. Starts the conversation."""
        cci = record.telnyx_call_control_id
        if not cci or not record.initial_message:
            return
        runtime.telnyx_phase = "speaking"
        try:
            await self.telnyx.speak(
                call_control_id=cci,
                text=record.initial_message,
                voice=settings.VOICE_CALL_TELNYX_TTS_VOICE,
                language=settings.VOICE_CALL_TELNYX_TTS_LANGUAGE,
            )
            _persist_turn_sync(str(record.id), speaker="bot", text=record.initial_message)
            logger.debug("Telnyx mode: spoke initial message for call %s", record.id)
        except Exception:
            logger.exception(
                "Telnyx speak (initial) failed for call %s", record.id
            )
            runtime.telnyx_phase = "idle"

    async def _telnyx_after_speak_ended(
        self, record: VoiceCall, runtime: CallRuntime
    ) -> None:
        """After bot finishes speaking, start listening for the user."""
        cci = record.telnyx_call_control_id
        if not cci:
            return
        # Don't restart transcription if we're already mid-thinking — that
        # means the user spoke and we're waiting on the agent.
        if runtime.telnyx_phase == "thinking":
            return
        runtime.telnyx_phase = "listening"
        runtime.pending_transcript = ""
        try:
            await self.telnyx.transcription_start(
                call_control_id=cci,
                language=settings.VOICE_CALL_TELNYX_STT_LANGUAGE,
                transcription_engine=settings.VOICE_CALL_TELNYX_STT_ENGINE,
            )
            logger.debug(
                "Telnyx mode: started transcription for call %s", record.id
            )
        except Exception:
            logger.exception(
                "Telnyx transcription_start failed for call %s", record.id
            )
            runtime.telnyx_phase = "idle"

    async def _telnyx_handle_transcription(
        self,
        record: VoiceCall,
        runtime: CallRuntime,
        inner: dict[str, Any],
    ) -> None:
        """Handle a Telnyx call.transcription event in Telnyx-only mode.

        Telnyx delivers transcription events with shape:
            {"transcription_data": {"transcript": "...", "is_final": true, ...}}

        Telnyx STT fires "final" at every micro-pause, so a sentence like
        "what are your capabilities" arrives as multiple final fragments
        ("what", " are", " your capabilities"). We accumulate fragments in
        ``runtime.pending_transcript`` and only fire the agent after a
        debounce window with no new fragments.
        """
        cci = record.telnyx_call_control_id
        if not cci:
            return

        transcription_data = inner.get("transcription_data") or {}
        transcript = (transcription_data.get("transcript") or "").strip()
        is_final = bool(transcription_data.get("is_final"))

        if not transcript:
            return
        if not is_final:
            return
        if runtime.telnyx_phase == "thinking":
            return

        # Append to the pending buffer.
        if runtime.pending_transcript:
            runtime.pending_transcript = runtime.pending_transcript + " " + transcript
        else:
            runtime.pending_transcript = transcript
        logger.debug(
            "Telnyx mode: transcript fragment for call %s: %r",
            record.id,
            transcript,
        )

        # Reset the debounce timer — cancel any in-flight one and start fresh.
        if runtime.transcript_debounce_task is not None and not runtime.transcript_debounce_task.done():
            runtime.transcript_debounce_task.cancel()

        runtime.transcript_debounce_task = asyncio.create_task(
            _telnyx_debounce_and_fire(
                call_id=str(record.id),
                cci=cci,
                debounce_ms=settings.VOICE_CALL_TRANSCRIPT_DEBOUNCE_MS,
            )
        )

    # ── Read-side ────────────────────────────────────────────────────────

    def get_call(self, call_id: str) -> Optional[CallView]:
        record = (
            self.db.query(VoiceCall)
            .filter(VoiceCall.id == call_id)
            .first()
        )
        if record is None:
            return None
        return _to_view(record)

    def list_calls(self, limit: int = 20) -> list[CallView]:
        rows = (
            self.db.query(VoiceCall)
            .order_by(VoiceCall.started_at.desc())
            .limit(limit)
            .all()
        )
        return [_to_view(r) for r in rows]


def _to_view(record: VoiceCall) -> CallView:
    return CallView(
        id=str(record.id),
        direction=record.direction,
        state=record.state,
        from_number=record.from_number,
        to_number=record.to_number,
        user_id=record.user_id,
        agent_id=record.agent_id,
        initial_message=record.initial_message,
        end_reason=record.end_reason,
        failure_error=record.failure_error,
        started_at=record.started_at,
        answered_at=record.answered_at,
        ended_at=record.ended_at,
        duration_ms=record.duration_ms,
        turns=[
            TurnView(
                turn_index=t.turn_index,
                speaker=t.speaker,
                text=t.text,
                started_at=t.started_at,
            )
            for t in sorted(record.turns, key=lambda x: x.turn_index)
        ],
    )


def _persist_turn_sync(call_id: str, *, speaker: str, text: str) -> None:
    """Insert a VoiceCallTurn row from outside a request context."""
    db = None
    try:
        db = SessionLocal()
        existing = (
            db.query(VoiceCallTurn).filter(VoiceCallTurn.call_id == call_id).count()
        )
        db.add(
            VoiceCallTurn(
                call_id=call_id,
                turn_index=existing,
                speaker=speaker,
                text=text,
            )
        )
        db.commit()
    except Exception:
        logger.exception("Failed to persist voice call turn for call %s", call_id)
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            db.close()


async def _telnyx_debounce_and_fire(
    *, call_id: str, cci: str, debounce_ms: int
) -> None:
    """Wait `debounce_ms` of silence, then fire the agent on the accumulated transcript.

    If a new transcript fragment arrives during the wait, the caller cancels
    this task and starts a new one — so the debounce window keeps resetting
    until the user actually stops talking.
    """
    try:
        await asyncio.sleep(debounce_ms / 1000.0)
    except asyncio.CancelledError:
        return  # New fragment arrived, our window restarted

    runtime = local_call_runtime.get(call_id)
    if runtime is None:
        return
    if runtime.telnyx_phase == "thinking":
        return
    transcript = (runtime.pending_transcript or "").strip()
    if not transcript:
        return

    logger.info("Call %s user (telnyx-stt): %r", call_id, transcript)
    runtime.pending_transcript = ""
    runtime.telnyx_phase = "thinking"

    # Stop transcription so it doesn't keep firing while the bot speaks.
    try:
        client = TelnyxClient()
        await client.transcription_stop(call_control_id=cci)
    except Exception:
        logger.warning(
            "transcription_stop failed for call %s — continuing", call_id
        )

    await _telnyx_agent_and_speak(call_id=call_id, cci=cci, transcript=transcript)


async def _telnyx_agent_and_speak(
    *, call_id: str, cci: str, transcript: str
) -> None:
    """Background driver for one Telnyx-mode user turn.

    1. Persist the user transcript
    2. Call the agent to get a reply
    3. Strip any tool-call markup from the reply
    4. Speak the reply via Telnyx /actions/speak (Polly)
    5. After speak.ended fires, the webhook handler will restart transcription

    Runs detached so the webhook handler can return 200 quickly.
    """
    runtime = local_call_runtime.get(call_id)
    if runtime is None:
        return

    _persist_turn_sync(call_id, speaker="user", text=transcript)

    if runtime.agent_session is None:
        logger.warning("No agent session for call %s in telnyx-mode handler", call_id)
        runtime.telnyx_phase = "idle"
        return

    try:
        reply = await run_agent_turn(runtime.agent_session, transcript)
    except Exception:
        logger.exception("Telnyx-mode agent turn failed for call %s", call_id)
        reply = "I hit an error. Could you try again?"

    # Strip tool-call XML the model may have embedded in the content.
    # Mirrors the sanitization in media_stream._sanitize_agent_reply.
    import re

    cleaned = re.sub(
        r"<tool_call>.*?</tool_call>|<function_call>.*?</function_call>",
        "",
        reply,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    if not cleaned:
        logger.warning(
            "Call %s agent reply was only tool-call markup — using fallback",
            call_id,
        )
        cleaned = "Let me think about that for a moment."

    logger.info("Call %s bot (telnyx-tts): %r", call_id, cleaned[:200])
    runtime.telnyx_phase = "speaking"
    _persist_turn_sync(call_id, speaker="bot", text=cleaned)
    try:
        client = TelnyxClient()
        await client.speak(
            call_control_id=cci,
            text=cleaned,
            voice=settings.VOICE_CALL_TELNYX_TTS_VOICE,
            language=settings.VOICE_CALL_TELNYX_TTS_LANGUAGE,
        )
    except Exception:
        logger.exception(
            "Telnyx /actions/speak failed for call %s reply", call_id
        )
        runtime.telnyx_phase = "idle"


# Note: ``_max_duration_timer`` was moved to ``media_stream.py`` so it runs
# on the WS owner worker (where it can find the local CallRuntime). The
# ``service.py`` ``initiate_outbound`` no longer starts an asyncio.Task here
# because that task would run on the wrong worker in multi-worker setups.
