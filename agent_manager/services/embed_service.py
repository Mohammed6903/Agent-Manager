"""Embedding service — supports OpenAI (text-embedding-3-small) and Gemini (gemini-embedding-001).

Uses a Redis-based global TPM counter so multiple Celery workers share one
budget instead of each tracking independently.
"""
from __future__ import annotations

import logging
import time

import redis

from ..config import settings

logger = logging.getLogger(__name__)

# ── Shared constants ─────────────────────────────────────────────────────────

_TOKENS_PER_WORD = 1.5
_MAX_429_RETRIES = 5

# ── OpenAI: text-embedding-3-small ───────────────────────────────────────────

# Global budget across ALL workers — 75% of OpenAI's 1M TPM hard limit
_OPENAI_TPM_BUDGET = 750_000
_OPENAI_MAX_INPUTS = 500

# ── Gemini: gemini-embedding-001 ─────────────────────────────────────────────

_GEMINI_MAX_INPUTS = 100

# ── Redis-based global TPM tracking ──────────────────────────────────────────

_REDIS_TPM_KEY = "openclaw:embed:tpm_tokens"
_REDIS_TPM_WINDOW_SECS = 60
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """Lazy Redis client for TPM tracking."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def _global_tpm_add(tokens: int) -> int:
    """Atomically add tokens to the global counter. Returns new total."""
    r = _get_redis()
    pipe = r.pipeline()
    pipe.incrby(_REDIS_TPM_KEY, tokens)
    pipe.expire(_REDIS_TPM_KEY, _REDIS_TPM_WINDOW_SECS)
    result = pipe.execute()
    return result[0]


def _global_tpm_get() -> int:
    """Read current global token count."""
    r = _get_redis()
    val = r.get(_REDIS_TPM_KEY)
    return int(val) if val else 0


def _wait_for_global_budget(needed_tokens: int) -> None:
    """Block until the global TPM budget has room for needed_tokens."""
    max_wait = 120  # seconds — don't block forever
    waited = 0.0
    while waited < max_wait:
        current = _global_tpm_get()
        if current + needed_tokens <= _OPENAI_TPM_BUDGET:
            return
        # Check TTL to know how long until the counter resets
        r = _get_redis()
        ttl = r.ttl(_REDIS_TPM_KEY)
        sleep_for = min(max(ttl, 2), 30)  # sleep 2-30s
        logger.info(
            "Global TPM budget: %d/%d used, need %d more. Waiting %ds (TTL=%d).",
            current, _OPENAI_TPM_BUDGET, needed_tokens, sleep_for, ttl,
        )
        time.sleep(sleep_for)
        waited += sleep_for

    logger.warning("Global TPM wait exceeded %ds — proceeding anyway.", max_wait)


# ── Module-level state (fallback for non-Redis environments) ─────────────────

_window_start: float = 0.0
_window_tokens: int = 0

# Lazy client handles — avoids importing SDKs that may not be installed for
# the active provider.
_openai_client = None  # openai.OpenAI
_gemini_client = None  # google.genai.Client


# ── Lazy client helpers ───────────────────────────────────────────────────────


def _get_openai():
    """Return (and lazily create) the shared OpenAI client."""
    global _openai_client
    from openai import OpenAI  # noqa: PLC0415

    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _get_gemini():
    """Return (and lazily create) the shared google-genai Client."""
    global _gemini_client
    import google.genai as genai  # noqa: PLC0415

    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client


# ── Token estimation ─────────────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Conservative token estimate: word count × _TOKENS_PER_WORD."""
    return len(text.split()) * _TOKENS_PER_WORD


# ── OpenAI implementation ─────────────────────────────────────────────────────


def _maybe_reset_window() -> None:
    """Reset the module-level OpenAI TPM window if 60 seconds have elapsed."""
    global _window_start, _window_tokens
    if time.monotonic() - _window_start >= 60.0:
        _window_start = time.monotonic()
        _window_tokens = 0


def _sleep_until_window_resets() -> None:
    """Block until the current 60-second window expires and resets."""
    global _window_start, _window_tokens
    elapsed = time.monotonic() - _window_start
    sleep_for = max(0.0, 60.0 - elapsed)
    if sleep_for > 0:
        logger.info(
            "TPM budget reached (%d tokens used). Sleeping %.1fs.",
            _window_tokens,
            sleep_for,
        )
        time.sleep(sleep_for)
    _window_start = time.monotonic()
    _window_tokens = 0


def _check_global_budget(batch_tokens: int) -> None:
    """Pre-check global Redis TPM budget before making an API call.
    Falls back to local-only tracking if Redis is unavailable."""
    try:
        _wait_for_global_budget(batch_tokens)
    except Exception as exc:
        logger.debug("Redis TPM check failed (using local-only): %s", exc)


def _embed_openai_batch(texts: list[str]) -> list[list[float]]:
    """Single OpenAI embeddings API call with exponential backoff on 429."""
    from openai import RateLimitError  # noqa: PLC0415

    for attempt in range(_MAX_429_RETRIES + 1):
        try:
            response = _get_openai().embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            return [e.embedding for e in sorted(response.data, key=lambda x: x.index)]
        except RateLimitError:
            if attempt == _MAX_429_RETRIES:
                raise
            delay = 2 ** (attempt + 1)  # 2 → 4 → 8 → 16 → 32 s
            logger.warning(
                "OpenAI embedding 429: retrying %d text(s) in %ds (attempt %d/%d).",
                len(texts),
                delay,
                attempt + 1,
                _MAX_429_RETRIES,
            )
            time.sleep(delay)
    return []  # pragma: no cover


def _embed_texts_openai(texts: list[str]) -> list[list[float]]:
    """TPM-aware batching for OpenAI with window-based rate limiting."""
    global _window_tokens

    vectors: list[list[float]] = [None] * len(texts)  # type: ignore[list-item]
    batch: list[str] = []
    batch_tokens = 0
    batch_indices: list[int] = []

    def _flush(b: list[str], indices: list[int], b_tokens: int) -> None:
        global _window_tokens
        # Global pre-check (Redis) — waits if cross-worker budget is full
        _check_global_budget(b_tokens)
        # Local per-worker window check
        _maybe_reset_window()
        if _window_tokens + b_tokens > _OPENAI_TPM_BUDGET:
            _sleep_until_window_resets()
        result = _embed_openai_batch(b)
        _window_tokens += b_tokens
        # Record in global counter
        try:
            _global_tpm_add(b_tokens)
        except Exception:
            pass  # Redis failure is non-fatal
        for idx, vec in zip(indices, result):
            vectors[idx] = vec

    for i, text in enumerate(texts):
        t_tokens = _estimate_tokens(text)
        if batch and (
            batch_tokens + t_tokens > _OPENAI_TPM_BUDGET
            or len(batch) >= _OPENAI_MAX_INPUTS
        ):
            _flush(batch, batch_indices, batch_tokens)
            batch, batch_tokens, batch_indices = [], 0, []
        batch.append(text)
        batch_tokens += t_tokens
        batch_indices.append(i)

    if batch:
        _flush(batch, batch_indices, batch_tokens)

    return vectors


# ── Gemini implementation ─────────────────────────────────────────────────────


def _embed_gemini_batch(texts: list[str]) -> list[list[float]]:
    """Single Gemini embed_content call with exponential backoff on 429.

    Uses the google-genai Client API. A 429 surfaces as ``ClientError`` with
    ``code == 429``.
    """
    from google.genai import types  # noqa: PLC0415
    from google.genai.errors import ClientError  # noqa: PLC0415

    client = _get_gemini()
    for attempt in range(_MAX_429_RETRIES + 1):
        try:
            response = client.models.embed_content(
                model="models/gemini-embedding-001",
                contents=texts,  # type: ignore[arg-type]
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            return [e.values for e in (response.embeddings or [])]  # type: ignore[misc]
        except ClientError as exc:
            if exc.code != 429 or attempt == _MAX_429_RETRIES:
                raise
            delay = 2 ** (attempt + 1)  # 2 → 4 → 8 → 16 → 32 s
            logger.warning(
                "Gemini embedding 429: retrying %d text(s) in %ds (attempt %d/%d).",
                len(texts),
                delay,
                attempt + 1,
                _MAX_429_RETRIES,
            )
            time.sleep(delay)
    return []  # pragma: no cover


def _embed_texts_gemini(texts: list[str]) -> list[list[float]]:
    """Batch Gemini embeddings, splitting into chunks of _GEMINI_MAX_INPUTS."""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _GEMINI_MAX_INPUTS):
        vectors.extend(_embed_gemini_batch(texts[i : i + _GEMINI_MAX_INPUTS]))
    return vectors


# ── Public API ────────────────────────────────────────────────────────────────


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed *texts* using the configured provider.

    Dispatches to OpenAI or Gemini based on ``settings.EMBEDDING_PROVIDER``.
    Each provider handles its own batching, TPM/quota tracking, and 429 backoff.

    Args:
        texts: Texts to embed. Order is preserved in the returned list.

    Returns:
        Float vectors in the same order as *texts*.
    """
    if not texts:
        return []
    if settings.EMBEDDING_PROVIDER == "gemini":
        return _embed_texts_gemini(texts)
    return _embed_texts_openai(texts)


def embed_texts_safe(texts: list[str]) -> list[list[float]]:
    """Thin alias — embed_texts already handles all batching internally."""
    return embed_texts(texts)


def embed_single(text: str) -> list[float]:
    """Embed a single text. Convenience wrapper."""
    return embed_texts([text])[0]
