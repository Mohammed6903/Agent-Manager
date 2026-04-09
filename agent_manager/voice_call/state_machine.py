"""Per-worker in-memory call runtime for voice calls.

This module holds the **process-local** part of each call's runtime — the
asyncio primitives and references that can't be shared across worker
processes (locks, events, tasks, the FastAPI WebSocket object, the rolling
agent message history). It is intentionally NOT shared across workers.

The cross-worker portion of call state (cci, encoding, agent_id,
initial_message, etc.) lives in Redis via :mod:`call_state_store`. Any
worker can look that up.

Architecture:

- POST /api/voice/call lands on Worker A. Worker A:
  1. Writes persistent state to Redis (call_state_store.create + set_cci)
  2. Calls Telnyx /calls
  3. Does NOT create a local CallRuntime — there's no audio loop yet,
     and the WS may land on a different worker

- Telnyx webhooks land on Worker B (or any worker via gunicorn round-robin).
  Worker B reads persistent state from Redis, updates DB, kicks off
  ``streaming_start`` if needed. Never touches the local registry.

- Telnyx opens the media stream WS to /api/voice/stream/{call_id}. The WS
  upgrade lands on Worker C. Worker C:
  1. Reads persistent state from Redis
  2. Creates a local CallRuntime in **its own** ``local_call_runtime``
     registry, populates from persistent state
  3. Runs the audio loop until the WS closes
  4. On disconnect, cleans up its local runtime and (optionally) deletes
     the Redis state

For voxtral mode this works cleanly because the entire audio + STT + agent
+ TTS loop happens inside the WS handler on Worker C — no other worker
needs the in-memory runtime for that call. Webhooks just update DB.

Telnyx-only mode (``VOICE_CALL_USE_VOXTRAL=False``) is more complex
because the conversation is driven by webhook events that may land on any
worker. For now that mode is **single-worker only**; the multi-worker
work in this PR focuses on voxtral mode.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .agent_bridge import VoiceAgentSession

logger = logging.getLogger(__name__)


@dataclass
class CallRuntime:
    """Per-worker, in-memory state for one active call.

    Constructed by the WebSocket owner worker when Telnyx connects the
    media stream. Holds the asyncio primitives and references that can't
    be serialized to Redis. Authoritative cross-worker state is in
    :mod:`call_state_store` (Redis); this struct mirrors a few fields
    locally for hot-path access without round-tripping.
    """

    call_id: str
    # Mirrored from Redis state for hot-path access. The Redis copy is the
    # source of truth — set on first read from `call_state_store.get(...)`.
    telnyx_call_control_id: Optional[str] = None
    media_encoding: str = "PCMU"
    # Sample rate of the inbound media track, as reported by Telnyx in the
    # streaming.start event's media_format.sample_rate. Defaults to 8 kHz
    # (the historical PCMU value); set to whatever Telnyx negotiates when
    # the start event arrives. Drives both the inbound frame_ms math and
    # the upsample-to-STT step in _handle_user_turn.
    inbound_sample_rate: int = 8000
    use_voxtral: bool = True
    direction: str = "outbound"
    initial_message: Optional[str] = None

    # Per-worker only — never serialized:
    agent_session: Optional[VoiceAgentSession] = None
    ws: Any = None  # fastapi.WebSocket — untyped to avoid import cycle
    stream_id: Optional[str] = None

    # Telnyx-only-mode bookkeeping (single-worker only path):
    telnyx_phase: str = "idle"  # idle | speaking | listening | thinking
    pending_transcript: str = ""
    transcript_debounce_task: Optional[Any] = None

    # Lock serializing speak↔listen transitions so we never try to STT our
    # own TTS output or speak while a turn is running. Per-call, per-worker.
    turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # Signalled once the initial message has finished playing.
    speaking_done: asyncio.Event = field(default_factory=asyncio.Event)

    # Whether we've already kicked off the opening greeting. Prevents races
    # when both `call.answered` and `streaming.started` events arrive.
    initial_message_sent: bool = False

    # Hard-cap timer — cancelled on clean hangup.
    max_duration_task: Optional[asyncio.Task] = None

    # The running loop task per call (listens → transcribes → agent → speaks).
    loop_task: Optional[asyncio.Task] = None


class LocalCallRuntime:
    """Per-process registry of active calls.

    Worker-local. Each gunicorn worker has its own instance and only sees
    the calls whose WebSocket connection landed on this worker. To find
    a call across workers, use :mod:`call_state_store` instead.
    """

    def __init__(self) -> None:
        self._by_call_id: Dict[str, CallRuntime] = {}

    def create(
        self,
        call_id: str,
        *,
        direction: str = "outbound",
        media_encoding: str = "PCMU",
        use_voxtral: bool = True,
        telnyx_call_control_id: Optional[str] = None,
        initial_message: Optional[str] = None,
    ) -> CallRuntime:
        runtime = CallRuntime(
            call_id=call_id,
            direction=direction,
            media_encoding=media_encoding,
            use_voxtral=use_voxtral,
            telnyx_call_control_id=telnyx_call_control_id,
            initial_message=initial_message,
        )
        self._by_call_id[call_id] = runtime
        return runtime

    def get(self, call_id: str) -> Optional[CallRuntime]:
        return self._by_call_id.get(call_id)

    def remove(self, call_id: str) -> None:
        rt = self._by_call_id.pop(call_id, None)
        if rt is None:
            return
        if rt.max_duration_task is not None and not rt.max_duration_task.done():
            rt.max_duration_task.cancel()
        if rt.loop_task is not None and not rt.loop_task.done():
            rt.loop_task.cancel()
        if (
            rt.transcript_debounce_task is not None
            and not rt.transcript_debounce_task.done()
        ):
            rt.transcript_debounce_task.cancel()

    def active_count(self) -> int:
        return len(self._by_call_id)


# Per-worker singleton. Each gunicorn worker imports this module and gets
# its own LocalCallRuntime — there's deliberately no cross-worker sharing
# of this registry. For cross-worker state lookups, use call_state_store.
local_call_runtime = LocalCallRuntime()

# Backward-compatibility alias — older code referenced ``voice_runtime``.
# All new code should use ``local_call_runtime``.
voice_runtime = local_call_runtime
