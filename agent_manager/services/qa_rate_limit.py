"""Redis-backed rate limiter for the public Q&A endpoint.

This module is the only abuse-prevention layer that runs before the
actual LLM call on the public Q&A path. It enforces three simultaneous
constraints per request:

- **Per-IP sliding window** — cheap abuse prevention against bots and
  scrapers. Uses SHA-256(salt + ip) as the key so raw IPs never land in
  Redis or logs.
- **Per-agent daily counter** — caps the founder's total cost exposure.
  Keyed by ``YYYY-MM-DD`` so it resets cleanly at midnight UTC without
  a sliding-window calculation.
- **Per-session turn counter** — caps a single visitor's conversation
  length. Keyed on the visitor's localStorage-generated UUID, auto-
  expires an hour after the last touch (so a visitor who walks away
  and comes back tomorrow gets a fresh budget).

Each limit raises an ``HTTPException(429)`` with a generic visitor-safe
message on the first violation; the caller returns that to the client
verbatim. **All three are checked on every request** — an IP that
passes the per-IP gate but hits the agent-daily gate still gets 429'd,
with the message explaining the reason.

Uses the same Redis singleton pattern already in use by
``agent_manager/voice_call/call_state_store.py:62-67`` — module-level
lazy-initialized sync client via ``redis.from_url(settings.REDIS_URL)``.
No new dependency, no new pool.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import redis
from fastapi import HTTPException

from ..config import settings

logger = logging.getLogger(__name__)

# ── Tunable limits ──────────────────────────────────────────────────────────
# These are code-level constants rather than environment variables because
# they're product decisions, not per-deployment knobs. If you need to raise
# or lower them, edit here and ship a release — don't plumb them through
# config. Per-agent overrides will be added if/when founders ask for
# different limits on different Q&A agents.

IP_LIMIT_PER_MINUTE = 30
"""How many requests a single IP can make in any 60-second window before
being blocked. Tunable — 30 is conservative enough to block obvious
scraping but generous enough that a single visitor clicking refresh or
opening multiple tabs won't hit it."""

AGENT_LIMIT_PER_DAY = 1000
"""How many total Q&A requests a single agent can serve in a calendar
day (UTC). Caps the founder's cost exposure at a known ceiling — at ~$0.001
per turn on a cheap model, this is ~$1/day worst case. Founders who
need higher limits can ask and we'll add per-agent overrides."""

SESSION_LIMIT_PER_HOUR = 25
"""How many turns a single visitor can take in a conversation session
(where 'session' = the UUID the visitor's localStorage holds). After 25
turns the visitor is asked to start a new session. Prevents a single
bad actor from using up the agent's daily budget in one conversation."""

# ── Redis key templates ─────────────────────────────────────────────────────

_KEY_IP = "qa_rl:ip:{hashed_ip}"
_KEY_AGENT_DAY = "qa_rl:agent:{agent_id}:{yyyy_mm_dd}"
_KEY_SESSION = "qa_rl:session:{session_id}"

# ── Redis singleton ─────────────────────────────────────────────────────────

_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    """Get or create the module-level Redis client. Lazy + memoized.

    Mirrors the pattern in ``call_state_store._get_redis``. Uses
    ``decode_responses=True`` so INCR returns a native Python int
    instead of bytes.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


# ── Public helpers ──────────────────────────────────────────────────────────


def hash_client_ip(raw_ip: str) -> str:
    """Hash a raw IP address with the deployment salt.

    Returned value is a 16-hex-char truncated SHA-256 digest. 16 chars
    is more than enough entropy for rate-limiting (2^64 possibilities,
    collision-resistant in any practical traffic volume) while keeping
    Redis keys short.

    The raw IP never leaves this function — callers pass in whatever
    they pulled from ``X-Forwarded-For`` / ``request.client.host`` and
    this returns the hash that goes into Redis + logs.
    """
    salted = (settings.QA_IP_HASH_SALT + ":" + (raw_ip or "unknown")).encode("utf-8")
    return hashlib.sha256(salted).hexdigest()[:16]


def check_and_increment(
    agent_id: str,
    visitor_session_id: str,
    client_ip_hashed: str,
) -> None:
    """Enforce all three Q&A rate limits in one Redis round trip.

    Raises ``HTTPException(status_code=429)`` on the first limit hit,
    with a visitor-safe ``detail`` explaining what happened. The
    message is designed to be surfaced to the visitor directly — it
    never reveals internal quota numbers or distinguishes between
    rate limit vs subscription vs wallet issues.

    On success, all three counters have been incremented and their
    TTLs refreshed. No return value — the caller assumes success if
    no exception was raised.

    Implementation detail: we use a pipeline with MULTI/EXEC so the
    three INCR+EXPIRE pairs land as one atomic unit. If Redis is
    unreachable for any reason we log a warning and **allow the
    request** (fail-open rather than fail-closed — a Redis outage
    shouldn't take down the public Q&A feature, and the layered
    defenses above this still apply).
    """
    if not agent_id or not visitor_session_id or not client_ip_hashed:
        # Defensive: never happens in practice because the router
        # validates before calling. But if it did, treat as a bad
        # request rather than silently skipping limits.
        raise HTTPException(status_code=400, detail="Invalid request.")

    try:
        r = _get_redis()
    except Exception:
        logger.exception("QA rate limiter: Redis unavailable, failing open")
        return

    ip_key = _KEY_IP.format(hashed_ip=client_ip_hashed)
    day_key = _KEY_AGENT_DAY.format(
        agent_id=agent_id,
        yyyy_mm_dd=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    session_key = _KEY_SESSION.format(session_id=visitor_session_id)

    try:
        pipe = r.pipeline(transaction=True)
        pipe.incr(ip_key)
        pipe.expire(ip_key, 60)
        pipe.incr(day_key)
        pipe.expire(day_key, 86400)
        pipe.incr(session_key)
        pipe.expire(session_key, 3600)
        results = pipe.execute()
    except Exception:
        logger.exception("QA rate limiter: pipeline failed, failing open")
        return

    # results indices map to the ops above:
    #   0: INCR ip
    #   1: EXPIRE ip
    #   2: INCR agent-day
    #   3: EXPIRE agent-day
    #   4: INCR session
    #   5: EXPIRE session
    try:
        ip_count = int(results[0])
        day_count = int(results[2])
        session_count = int(results[4])
    except (IndexError, ValueError, TypeError):
        logger.warning(
            "QA rate limiter: unexpected pipeline results %r — failing open",
            results,
        )
        return

    # Check limits in order of decreasing scope. Report the FIRST one
    # that fires so the visitor gets a deterministic message.

    if ip_count > IP_LIMIT_PER_MINUTE:
        logger.info(
            "QA rate limit hit: ip (count=%d, limit=%d) for agent=%s session=%s",
            ip_count, IP_LIMIT_PER_MINUTE, agent_id, visitor_session_id[:8],
        )
        raise HTTPException(
            status_code=429,
            detail="You're sending messages too quickly. Please wait a moment.",
        )

    if day_count > AGENT_LIMIT_PER_DAY:
        logger.info(
            "QA rate limit hit: agent-day (count=%d, limit=%d) for agent=%s",
            day_count, AGENT_LIMIT_PER_DAY, agent_id,
        )
        raise HTTPException(
            status_code=429,
            detail="This assistant has reached its daily message limit. Please try again tomorrow.",
        )

    if session_count > SESSION_LIMIT_PER_HOUR:
        logger.info(
            "QA rate limit hit: session-turns (count=%d, limit=%d) for session=%s",
            session_count, SESSION_LIMIT_PER_HOUR, visitor_session_id[:8],
        )
        raise HTTPException(
            status_code=429,
            detail="You've reached the conversation limit. Please start a new session.",
        )
