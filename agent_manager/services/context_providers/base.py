"""Abstract base for integration context providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from celery import Task
from sqlalchemy.orm import Session


class IntegrationContextProvider(ABC):
    """Contract that every third-party context integration must satisfy.

    The service layer, Celery tasks, context injection, and S3/Qdrant
    helpers all resolve integration-specific behaviour through this
    interface — no ``if integration == "X"`` branching required.
    """

    # ── Identity ──────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable integration key stored in ThirdPartyContext.integration_name."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable label (e.g. "Gmail", "Google Calendar")."""

    @property
    @abstractmethod
    def dedup_key(self) -> str:
        """Qdrant payload field used to deduplicate search results.

        Gmail uses ``"message_id"``, Calendar uses ``"event_id"``, etc.
        """

    # ── Credential verification ───────────────────────────────────────────

    @abstractmethod
    def verify_credentials(self, db: Session, agent_id: str) -> bool:
        """Return True if the agent has valid, usable credentials."""

    # ── Celery task references ────────────────────────────────────────────

    @abstractmethod
    def get_ingest_task(self) -> Task:
        """Return the Celery task that ingests + pipelines data."""

    @abstractmethod
    def get_delete_task(self) -> Task:
        """Return the Celery task that deletes context data."""

    # ── Snapshot & formatting (used by context injection) ─────────────────

    @abstractmethod
    def snapshot(self, agent_id: str, hours: int) -> list[dict]:
        """Return recent/upcoming items for passive context injection."""

    @abstractmethod
    def format_snapshot_lines(self, results: list[dict], max_items: int = 10) -> list[str]:
        """Format snapshot results as compact one-liner summaries."""

    @abstractmethod
    def format_semantic_lines(
        self, results: list[dict], max_items: int = 5, snippet_max_len: int = 200,
    ) -> list[str]:
        """Format semantic search results with truncated snippets."""

    @abstractmethod
    def context_block_header(self) -> str:
        """Section header for the injected context block (e.g. ``--- Email Context ---``)."""

    @abstractmethod
    def snapshot_label(self) -> str:
        """Label shown above the snapshot section (e.g. ``Recent activity (last 24h):``)."""

    @abstractmethod
    def semantic_label(self) -> str:
        """Label shown above the semantic section (e.g. ``Relevant emails for your query:``)."""

    @abstractmethod
    def context_block_footer(self) -> str:
        """Section footer (e.g. ``--------------------``)."""

    # ── Default snapshot hours ────────────────────────────────────────────

    @property
    def default_snapshot_hours(self) -> int:
        """How many hours of data the snapshot covers (override per-provider)."""
        return 24

    # ── Ingest hooks (used by the generic Celery task) ────────────────────

    @property
    @abstractmethod
    def s3_integration_key(self) -> str:
        """S3 namespace segment (e.g. ``"gmail"``, ``"calendar"``)."""

    @property
    @abstractmethod
    def qdrant_source(self) -> str:
        """Value stored in Qdrant payload ``source`` field."""

    @property
    @abstractmethod
    def expired_sync_cursor_http_code(self) -> int:
        """HTTP status code the API returns when the sync cursor is stale.

        Gmail returns 404 (historyId too old), Calendar returns 410 (syncToken gone).
        """

    @abstractmethod
    def build_api_service(self, credentials: Any) -> Any:
        """Build the authenticated Google API service object."""

    @abstractmethod
    def get_account_email(self, api_service: Any) -> str:
        """Extract the account email from the API service."""

    @abstractmethod
    def full_sync(
        self, api_service: Any, agent_id: str, counters: dict[str, int],
        is_aborted: Any,
    ) -> str | None:
        """Run a full ingest from scratch. Returns the sync cursor, or None if aborted."""

    @abstractmethod
    def incremental_sync(
        self, api_service: Any, agent_id: str, cursor: str,
        counters: dict[str, int], is_aborted: Any,
    ) -> str | None:
        """Run an incremental ingest from a cursor. Returns the new cursor, or None if aborted."""

    @abstractmethod
    def list_s3_item_ids(self, agent_id: str) -> list[str]:
        """List item IDs stored in S3 for this agent."""

    @abstractmethod
    def load_s3_batch(self, agent_id: str, item_ids: list[str]) -> list[dict]:
        """Load a batch of items from S3."""

    @abstractmethod
    def pipeline_batch(
        self, items: list[dict], agent_id: str, account_email: str,
    ) -> None:
        """Run the embed+upsert pipeline on a batch of items."""

    @abstractmethod
    def pipeline_single(
        self, item: dict, agent_id: str, account_email: str,
    ) -> None:
        """Run the embed+upsert pipeline on a single item (fallback)."""

    @abstractmethod
    def delete_s3_data(self, agent_id: str, task_id: str, update_progress: Any) -> int:
        """Delete all S3 data for this agent. Returns count of deleted objects."""
