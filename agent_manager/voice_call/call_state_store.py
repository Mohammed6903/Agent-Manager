"""Redis-backed cross-worker store for active voice-call state.

OpenClawApi runs under gunicorn with multiple uvicorn workers in production.
Telnyx webhooks for a given call land on whichever worker the load balancer
picks (round-robin), and the media-stream WebSocket connection lands on yet
another worker. So in-memory state in any single worker is invisible to the
others.

This module fixes that by storing the **persistent** part of each call's
state in Redis, indexed by both our internal ``call_id`` and Telnyx's
``call_control_id``. Any worker can look up call info regardless of which
worker initiated it.

What lives here (cross-worker, persistent):

- ``call_id`` ↔ ``telnyx_call_control_id`` mapping
- The negotiated G.711 ``media_encoding`` (PCMU / PCMA, set on first WS frame)
- ``stream_id`` (Telnyx media stream identifier)
- The seed data the WebSocket owner worker needs to bootstrap the audio loop:
  ``agent_id``, ``system_prompt``, ``initial_message``, ``use_voxtral``
- Telnyx-only mode bookkeeping (``telnyx_phase``, ``pending_transcript``)

What does NOT live here (per-worker, in-memory only):

- ``asyncio.Lock`` (turn_lock)
- ``asyncio.Event`` (speaking_done)
- ``asyncio.Task`` (max_duration_task, loop_task)
- The ``WebSocket`` object itself
- ``VoiceAgentSession`` (the rolling agent message history) — for voxtral mode
  this lives in the WS owner's memory because all turns happen on that worker

Sync ``redis`` client (matches the project pattern in
``services/embed_service.py`` and the ``tasks/`` modules). Sub-millisecond
ops, fine to call from async code in our use case (1-2 ops per webhook,
not in the audio hot path).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis

from ..config import settings

logger = logging.getLogger(__name__)

# 1 hour TTL — longer than VOICE_CALL_MAX_DURATION_SEC so state outlives any
# real call. Stale entries get cleaned up automatically.
_DEFAULT_TTL_SEC = 3600

# Redis key patterns
_KEY_STATE = "voice_call:state:{call_id}"        # hash of call's persistent fields
_KEY_CCI_TO_ID = "voice_call:cci:{cci}"          # cci → call_id (string)


_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    """Get or create the module-level Redis client. Lazy + memoized."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def _state_key(call_id: str) -> str:
    return _KEY_STATE.format(call_id=call_id)


def _cci_key(cci: str) -> str:
    return _KEY_CCI_TO_ID.format(cci=cci)


def _to_redis(value: Any) -> str:
    """Serialize a Python value to a Redis string field.

    JSON for everything except plain strings, booleans, and ints — keeps
    the wire format readable for debugging via ``redis-cli HGETALL``.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value)


def _from_redis(value: Optional[str], expected_type: type = str) -> Any:
    if value is None or value == "":
        return None
    if expected_type is bool:
        return value == "1"
    if expected_type is int:
        return int(value)
    if expected_type is float:
        return float(value)
    if expected_type is str:
        return value
    # Treat as JSON for dict / list
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def create(
    *,
    call_id: str,
    direction: str,
    use_voxtral: bool,
    agent_id: Optional[str],
    user_id: Optional[str],
    initial_message: Optional[str],
    system_prompt: Optional[str],
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    """Initialize a new call's persistent state in Redis.

    Called from ``VoiceCallService.initiate_outbound`` BEFORE the Telnyx
    POST /calls request, so any worker that receives the resulting
    webhooks can find the call.
    """
    r = _get_redis()
    fields = {
        "call_id": call_id,
        "direction": direction,
        "use_voxtral": _to_redis(use_voxtral),
        "agent_id": _to_redis(agent_id),
        "user_id": _to_redis(user_id),
        "initial_message": _to_redis(initial_message),
        "system_prompt": _to_redis(system_prompt),
        "telnyx_call_control_id": "",
        "stream_id": "",
        "media_encoding": "PCMU",  # default, overridden on first WS start event
        "initial_message_sent": "0",
        "telnyx_phase": "idle",
        "pending_transcript": "",
    }
    key = _state_key(call_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping=fields)
    pipe.expire(key, ttl_sec)
    pipe.execute()


def set_cci(*, call_id: str, cci: str, ttl_sec: int = _DEFAULT_TTL_SEC) -> None:
    """Record the Telnyx call_control_id and create the cci → call_id index.

    Called right after the Telnyx /calls API responds. Two writes (state
    hash field + cci index entry) so webhook handlers can resolve in either
    direction.
    """
    r = _get_redis()
    pipe = r.pipeline()
    pipe.hset(_state_key(call_id), "telnyx_call_control_id", cci)
    pipe.set(_cci_key(cci), call_id, ex=ttl_sec)
    pipe.execute()


def update(
    call_id: str,
    fields: dict[str, Any],
    *,
    refresh_ttl: bool = True,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    """Update one or more fields of a call's persistent state.

    Boolean / numeric / dict / list values are auto-serialized.
    """
    if not fields:
        return
    r = _get_redis()
    serialized = {k: _to_redis(v) for k, v in fields.items()}
    key = _state_key(call_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping=serialized)
    if refresh_ttl:
        pipe.expire(key, ttl_sec)
    pipe.execute()


def get(call_id: str) -> Optional[dict[str, Any]]:
    """Read all persistent fields for a call. Returns None if not found.

    The returned dict has type-converted values: ``use_voxtral`` and
    ``initial_message_sent`` are bools, ``call_id`` etc. are strings.
    """
    r = _get_redis()
    raw = r.hgetall(_state_key(call_id))
    if not raw:
        return None
    return _decode_state(raw)


def get_call_id_by_cci(cci: str) -> Optional[str]:
    """Reverse lookup from Telnyx call_control_id to our internal call_id.

    Used by the webhook handler — Telnyx events arrive with the cci, we
    need to find which of our calls owns it.
    """
    r = _get_redis()
    return r.get(_cci_key(cci))


def get_by_cci(cci: str) -> Optional[dict[str, Any]]:
    """Convenience: lookup full call state by Telnyx call_control_id."""
    call_id = get_call_id_by_cci(cci)
    if not call_id:
        return None
    return get(call_id)


def delete(call_id: str) -> None:
    """Remove a call's persistent state from Redis.

    Called when the call ends cleanly. The cci index entry is also
    removed if we know the cci. Stale entries (in case of process crash)
    are cleaned up by the TTL.
    """
    r = _get_redis()
    state = r.hgetall(_state_key(call_id))
    pipe = r.pipeline()
    pipe.delete(_state_key(call_id))
    cci = state.get("telnyx_call_control_id") if state else None
    if cci:
        pipe.delete(_cci_key(cci))
    pipe.execute()


def _decode_state(raw: dict[str, str]) -> dict[str, Any]:
    """Convert raw Redis hash strings back to typed Python values."""
    return {
        "call_id": _from_redis(raw.get("call_id")),
        "direction": _from_redis(raw.get("direction")),
        "use_voxtral": _from_redis(raw.get("use_voxtral"), bool) or False,
        "agent_id": _from_redis(raw.get("agent_id")),
        "initial_message": _from_redis(raw.get("initial_message")),
        "system_prompt": _from_redis(raw.get("system_prompt")),
        "telnyx_call_control_id": _from_redis(raw.get("telnyx_call_control_id")),
        "stream_id": _from_redis(raw.get("stream_id")),
        "media_encoding": _from_redis(raw.get("media_encoding")) or "PCMU",
        "initial_message_sent": _from_redis(raw.get("initial_message_sent"), bool)
        or False,
        "telnyx_phase": _from_redis(raw.get("telnyx_phase")) or "idle",
        "pending_transcript": _from_redis(raw.get("pending_transcript")) or "",
    }
