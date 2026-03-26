"""Celery task for bulk Gmail ingestion → S3 + Qdrant pipeline."""
from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import google_auth_httplib2
import httplib2
import redis as redis_lib
from celery import current_task
from googleapiclient.errors import HttpError

from agent_manager.config import settings
from agent_manager.services import s3_service
from agent_manager.integrations.google.gmail.service import _parse_message

logger = logging.getLogger(__name__)

# Gmail's hard maximum is 100 sub-requests per batch envelope
_BATCH_SIZE = 75
# How many batch HTTP requests to fire in parallel per round
_MAX_CONCURRENT_BATCHES = 5
# Short courtesy pause between concurrent rounds (not between every batch)
_INTER_ROUND_DELAY: float = 1.0
# Max retries for individual messages that return HTTP 429
_MAX_429_RETRIES = 6

# Redis hash that maps "integration:agent_id" -> task_id for in-flight jobs.
_ACTIVE_KEY = "openclaw:ingest:active"
# Safety TTL so stale entries don't accumulate if the worker crashes
_ACTIVE_TTL = 86_400  # 24 hours


# ── Active-task Registry ──────────────────────────────────────────────────────


def _redis() -> redis_lib.Redis:
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _active_field(agent_id: str, integration_name: str = "gmail", task_type: str = "ingest") -> str:
    """Build a stable Redis hash field for a single integration + agent pair + task type."""
    return f"{integration_name}:{task_type}:{agent_id}"


def register_active_task(agent_id: str, task_id: str, task_type: str = "ingest") -> None:
    """Record that *task_id* is actively working for *agent_id*."""
    r = _redis()
    r.hset(_ACTIVE_KEY, _active_field(agent_id, task_type=task_type), task_id)
    r.expire(_ACTIVE_KEY, _ACTIVE_TTL)


def unregister_active_task(agent_id: str, task_id: str, task_type: str = "ingest") -> None:
    """Remove active entry only if it still points at *task_id*."""
    field = _active_field(agent_id, task_type=task_type)
    r = _redis()
    current = r.hget(_ACTIVE_KEY, field)
    if current == task_id:
        r.hdel(_ACTIVE_KEY, field)


def get_active_tasks() -> dict[str, str]:
    """Return {integration:agent_id -> task_id} for active ingestion jobs."""
    data = _redis().hgetall(_ACTIVE_KEY)
    return {str(k): str(v) for k, v in data.items()}


# ── HTTP Transport ────────────────────────────────────────────────────────────


def _make_http(credentials: Any) -> Any:
    """Create a fresh per-thread authorized HTTP transport.

    ``google_auth_httplib2.AuthorizedHttp`` wraps a brand-new ``httplib2.Http``
    so concurrent threads each have an independent connection — no shared state.
    """
    return google_auth_httplib2.AuthorizedHttp(credentials, httplib2.Http())


# ── Progress Helpers ─────────────────────────────────────────────────────────


def _update_progress(task_state: str, meta: dict[str, Any]) -> None:
    """Push progress update to Celery backend (Redis).

    Must be called from the main worker thread — Celery's ``current_task``
    proxy uses thread-local storage and is not visible in spawned threads.
    """
    current_task.update_state(state=task_state, meta=meta)


def _emit(counters: dict[str, int], total: int) -> None:
    """Emit a FETCHING progress event with the current counters."""
    current = counters["fetched"]
    percentage = int((current / total * 100) if total > 0 else 0)
    _update_progress(
        "FETCHING",
        {
            "stage": "fetching",
            "message": f"Fetching emails ({current}/{total})...",
            "current": current,
            "total": total,
            "percentage": percentage,
            "skipped": counters["skipped"],
            "failed": counters["failed"],
        },
    )


# ── Batch Helper ──────────────────────────────────────────────────────────────


def _fetch_batch(
    service: Any,
    agent_id: str,
    message_ids: list[str],
    counters: dict[str, int],
    total: int,
    is_aborted: Callable[[], bool] | None = None,
    credentials: Any = None,
    counter_lock: threading.Lock | None = None,
) -> None:
    """Execute one batch HTTP request (up to _BATCH_SIZE messages) and store results in S3.

    Thread-safe: counter mutations are guarded by *counter_lock*. A fresh
    per-thread HTTP transport is created from *credentials* so this function
    can be called concurrently from a ``ThreadPoolExecutor``.

    Messages that are rate-limited (HTTP 429) are automatically retried up to
    _MAX_429_RETRIES times with exponential back-off (2 → 4 → 8 → 16 s).

    Args:
        service: Authenticated Gmail API service instance (shared, read-only use only).
        agent_id: Owner of the messages, used as the S3 key prefix.
        message_ids: IDs to fetch; should be <= _BATCH_SIZE in length.
        counters: Mutable dict with keys 'fetched', 'skipped', 'failed'.
        total: Total message estimate, used only for progress reporting.
        is_aborted: Optional callable; when True the batch exits early.
        credentials: Google OAuth credentials for creating a per-thread HTTP transport.
        counter_lock: Lock that guards all writes to *counters*.
    """
    _lock = counter_lock or threading.Lock()
    pending: list[str] = list(message_ids)

    for attempt in range(_MAX_429_RETRIES + 1):
        if not pending:
            break
        if is_aborted and is_aborted():
            with _lock:
                counters["failed"] += len(pending)
            return
        if attempt > 0:
            base = 2 ** attempt  # 2 → 4 → 8 → 16 → 32 → 64s
            jitter = random.uniform(0, base * 0.5)
            delay = base + jitter
            logger.info(
                "Rate-limited: retrying %d message(s) in %.1fs (attempt %d/%d).",
                len(pending), delay, attempt, _MAX_429_RETRIES,
            )
            time.sleep(delay)

        # Collect 429-throttled IDs so we can retry them in the next iteration
        throttled: list[str] = []
        batch = service.new_batch_http_request()

        def _on_message(
            request_id: str,
            response: dict[str, Any] | None,
            exception: Exception | None,
            _throttled: list[str] = throttled,
        ) -> None:
            if exception is not None:
                if isinstance(exception, HttpError) and exception.status_code == 429:
                    _throttled.append(request_id)
                    return
                with _lock:
                    counters["failed"] += 1
                logger.warning("Batch: failed to fetch message %s: %s", request_id, exception)
            else:
                parsed = _parse_message(response)
                clean = {
                    k: parsed[k]
                    for k in (
                        "id", "threadId", "labelIds", "subject",
                        "from", "to", "cc", "date", "snippet", "body",
                    )
                    if k in parsed
                }
                clean["has_attachment"] = bool(parsed.get("attachments"))
                s3_service.save_gmail_raw(agent_id, request_id, clean)
                with _lock:
                    counters["fetched"] += 1
            # Progress emission is intentionally omitted here — _emit uses
            # current_task which is thread-local to the main worker thread.
            # Callers emit progress after each concurrent round instead.

        for message_id in pending:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=message_id,
                    format="full",
                    fields="id,threadId,labelIds,snippet,payload/headers,payload/parts,payload/body",
                ),
                callback=_on_message,
                request_id=message_id,
            )

        # Use a fresh per-thread HTTP transport for thread-safe concurrent execution
        thread_http = _make_http(credentials) if credentials else None
        if thread_http:
            batch.execute(http=thread_http)
        else:
            batch.execute()

        pending = throttled

    for message_id in pending:
        with _lock:
            counters["failed"] += 1
        logger.warning(
            "Gave up on message %s after %d rate-limit retries.",
            message_id, _MAX_429_RETRIES,
        )


# ── Concurrent Batch Runner ───────────────────────────────────────────────────


def _run_concurrent_batches(
    service: Any,
    agent_id: str,
    message_ids: list[str],
    counters: dict[str, int],
    total: int,
    is_aborted: Callable[[], bool],
    credentials: Any,
    counter_lock: threading.Lock,
) -> bool:
    """Execute all batch requests using a thread pool, _MAX_CONCURRENT_BATCHES at a time.

    Progress is emitted after each round on the calling (main worker) thread so
    that Celery's ``current_task`` proxy resolves correctly.

    Returns:
        True if all batches completed, False if aborted mid-way.
    """
    batches = [
        message_ids[i : i + _BATCH_SIZE]
        for i in range(0, len(message_ids), _BATCH_SIZE)
    ]
    total_rounds = (len(batches) + _MAX_CONCURRENT_BATCHES - 1) // _MAX_CONCURRENT_BATCHES

    for round_idx, round_start in enumerate(range(0, len(batches), _MAX_CONCURRENT_BATCHES)):
        if is_aborted():
            return False

        round_batches = batches[round_start : round_start + _MAX_CONCURRENT_BATCHES]
        logger.debug(
            "Batch round %d/%d: dispatching %d concurrent batch(es) (%d messages).",
            round_idx + 1, total_rounds, len(round_batches),
            sum(len(b) for b in round_batches),
        )

        with ThreadPoolExecutor(max_workers=len(round_batches)) as pool:
            futures = []
            for batch in round_batches:
                futures.append(pool.submit(
                    _fetch_batch,
                    service, agent_id, batch, counters, total,
                    is_aborted, credentials, counter_lock,
                ))
            round_error: Exception | None = None
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    # Log but collect — let remaining futures in this round finish
                    # before re-raising so partial progress (counters) is preserved.
                    logger.exception("Concurrent batch execution raised an unhandled error.")
                    if round_error is None:
                        round_error = exc

        if round_error is not None:
            # Re-raise so the Celery task fails properly and retries. This
            # prevents a broken sync from saving a historyId as if it succeeded.
            raise round_error

        # Emit progress from the main thread after each round
        _emit(counters, total)

        if round_start + _MAX_CONCURRENT_BATCHES < len(batches):
            time.sleep(_INTER_ROUND_DELAY)

    return True


# ── Sync Strategies ───────────────────────────────────────────────────────────


def _full_sync(
    service: Any,
    agent_id: str,
    total_estimate: int,
    counters: dict[str, int],
    is_aborted: Callable[[], bool],
    credentials: Any = None,
    counter_lock: threading.Lock | None = None,
) -> str | None:
    """Page through all message IDs and batch-fetch those not already in S3.

    First collects all unfetched message IDs (pagination scan), then fires
    concurrent batch requests (_MAX_CONCURRENT_BATCHES at a time) for maximum
    throughput. The S3 pre-scan is a single ListObjectsV2 call so per-message
    existence checks are O(1) in-memory lookups.

    Args:
        service: Authenticated Gmail API service instance.
        agent_id: Agent whose mailbox is being synced.
        total_estimate: Approximate message count from the profile call (for progress).
        counters: Mutable dict with keys 'fetched', 'skipped', 'failed'.
        is_aborted: Callable that returns True if the task has been cancelled.
        credentials: Google OAuth credentials for per-thread HTTP transports.
        counter_lock: Shared lock for thread-safe counter updates.

    Returns:
        The current historyId, or None if the task was cancelled mid-sync.
    """
    _lock = counter_lock or threading.Lock()

    _update_progress(
        "FETCHING",
        {
            "stage": "scanning",
            "message": "Scanning already-stored emails...",
            "current": 0,
            "total": total_estimate,
            "percentage": 0,
            "skipped": 0,
            "failed": 0,
        },
    )
    stored_status: dict[str, bool] = s3_service.list_all_gmail_message_ids_with_status(agent_id)

    # ── Phase 1+2: Paginate message IDs in chunks and fetch concurrently ─────
    # Process IDs in chunks of _ID_CHUNK_SIZE to avoid unbounded memory usage
    # on large mailboxes (500k+ messages).
    _ID_CHUNK_SIZE = 10_000
    all_to_fetch: list[str] = []
    page_token: str | None = None
    total_fetched_ids = 0

    while True:
        if is_aborted():
            return None

        kwargs: dict[str, Any] = {"userId": "me", "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().messages().list(**kwargs).execute()
        message_refs: list[dict[str, Any]] = response.get("messages", [])

        if not message_refs:
            break

        to_fetch: list[str] = []
        to_restore: list[str] = []

        for ref in message_refs:
            msg_id = ref["id"]
            if msg_id not in stored_status:
                to_fetch.append(msg_id)
            elif stored_status[msg_id]:
                to_restore.append(msg_id)
            else:
                counters["skipped"] += 1

        if to_restore:
            restored = s3_service.untag_gmail_as_expired(agent_id, to_restore)
            with _lock:
                counters["fetched"] += restored
            for r_id in to_restore:
                stored_status[r_id] = False

        all_to_fetch.extend(to_fetch)

        # When chunk is full, flush it: fetch concurrently then clear the list
        if len(all_to_fetch) >= _ID_CHUNK_SIZE:
            chunk_total = len(all_to_fetch) + counters["skipped"]
            _update_progress(
                "FETCHING",
                {
                    "stage": "fetching",
                    "message": f"Fetching emails (chunk of {len(all_to_fetch)})...",
                    "current": counters["fetched"],
                    "total": total_estimate,
                    "percentage": int((counters["fetched"] / total_estimate * 100) if total_estimate else 0),
                    "skipped": counters["skipped"],
                    "failed": counters["failed"],
                },
            )
            completed = _run_concurrent_batches(
                service, agent_id, all_to_fetch, counters, total_estimate, is_aborted, credentials, _lock
            )
            if not completed:
                return None
            total_fetched_ids += len(all_to_fetch)
            all_to_fetch.clear()

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    # Flush remaining IDs
    if all_to_fetch:
        actual_total = total_fetched_ids + len(all_to_fetch) + counters["skipped"]
        _update_progress(
            "FETCHING",
            {
                "stage": "fetching",
                "message": f"Fetching {len(all_to_fetch)} new emails...",
                "current": counters["fetched"],
                "total": actual_total,
                "percentage": int((counters["fetched"] / actual_total * 100) if actual_total else 0),
                "skipped": counters["skipped"],
                "failed": 0,
            },
        )
        completed = _run_concurrent_batches(
            service, agent_id, all_to_fetch, counters, actual_total, is_aborted, credentials, _lock
        )
        if not completed:
            return None

    profile = service.users().getProfile(userId="me").execute()
    return profile["historyId"]


def _incremental_sync(
    service: Any,
    agent_id: str,
    history_id: str,
    counters: dict[str, int],
    is_aborted: Callable[[], bool],
    credentials: Any = None,
    counter_lock: threading.Lock | None = None,
) -> str | None:
    """Fetch only messages added since *history_id* via the Gmail History API.

    Collects all added message IDs by paginating history, then fires concurrent
    batch requests to fetch those not already in S3.

    Args:
        service: Authenticated Gmail API service instance.
        agent_id: Agent whose mailbox is being synced.
        history_id: The historyId stored from the last successful sync.
        counters: Mutable dict with keys 'fetched', 'skipped', 'failed'.
        is_aborted: Callable that returns True if the task has been cancelled.
        credentials: Google OAuth credentials for per-thread HTTP transports.
        counter_lock: Shared lock for thread-safe counter updates.

    Returns:
        The new historyId, or None if the task was cancelled mid-sync.

    Raises:
        HttpError: Propagated as-is so the caller can handle 404 (history too old)
            by falling back to a full sync.
    """
    _lock = counter_lock or threading.Lock()
    page_token: str | None = None
    new_history_id: str = history_id
    to_fetch: list[str] = []

    stored_status: dict[str, bool] = s3_service.list_all_gmail_message_ids_with_status(agent_id)

    # ── Collect all added message IDs from history ───────────────────────────
    while True:
        if is_aborted():
            return None

        kwargs: dict[str, Any] = {
            "userId": "me",
            "startHistoryId": history_id,
            "historyTypes": ["messageAdded"],
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().history().list(**kwargs).execute()
        new_history_id = response.get("historyId", new_history_id)
        
        to_restore: list[str] = []

        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                msg_id: str = added["message"]["id"]
                
                if msg_id not in stored_status:
                    to_fetch.append(msg_id)
                elif stored_status[msg_id]:
                    # Exists but is expired, restore it
                    to_restore.append(msg_id)
                else:
                    # Exists and is active
                    counters["skipped"] += 1
                    
        if to_restore:
            restored = s3_service.untag_gmail_as_expired(agent_id, to_restore)
            with _lock:
                counters["fetched"] += restored
            # Update local state cache
            for r_id in to_restore:
                stored_status[r_id] = False

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    total_estimate = len(to_fetch) + counters["skipped"]

    # ── Concurrent batch-fetch the new messages ───────────────────────────────
    completed = _run_concurrent_batches(
        service, agent_id, to_fetch, counters, total_estimate, is_aborted, credentials, _lock
    )
    if not completed:
        return None

    return new_history_id