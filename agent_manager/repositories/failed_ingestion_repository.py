"""Repository for the Dead Letter Queue (failed ingestion items)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.failed_ingestion import FailedIngestion

logger = logging.getLogger("agent_manager.repositories.failed_ingestion")

# Max retries before marking permanently failed
MAX_RETRIES = 5
# Backoff schedule in hours: 1h, 4h, 12h, 24h, 48h
BACKOFF_HOURS = [1, 4, 12, 24, 48]


class FailedIngestionRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(
        self,
        agent_id: str,
        integration_name: str,
        message_id: str,
        phase: str,
        error: str | None = None,
    ) -> FailedIngestion:
        """Add a failed item to the DLQ. Skips if already pending for this message."""
        existing = (
            self.db.query(FailedIngestion)
            .filter(
                FailedIngestion.agent_id == agent_id,
                FailedIngestion.integration_name == integration_name,
                FailedIngestion.message_id == message_id,
                FailedIngestion.status.in_(["pending", "retrying"]),
            )
            .first()
        )
        if existing:
            return existing

        entry = FailedIngestion(
            agent_id=agent_id,
            integration_name=integration_name,
            message_id=message_id,
            phase=phase,
            error=str(error)[:2000] if error else None,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        logger.info("DLQ: added %s/%s/%s (phase=%s)", agent_id, integration_name, message_id, phase)
        return entry

    def list_retryable(self, limit: int = 100) -> List[FailedIngestion]:
        """Return items eligible for retry (pending/retrying, within retry limit, backoff elapsed)."""
        now = datetime.now(timezone.utc)
        items = (
            self.db.query(FailedIngestion)
            .filter(
                FailedIngestion.status.in_(["pending", "retrying"]),
                FailedIngestion.retry_count < MAX_RETRIES,
            )
            .order_by(FailedIngestion.created_at.asc())
            .limit(limit * 2)  # over-fetch to filter by backoff
            .all()
        )

        retryable = []
        for item in items:
            if len(retryable) >= limit:
                break
            backoff_idx = min(item.retry_count, len(BACKOFF_HOURS) - 1)
            backoff = timedelta(hours=BACKOFF_HOURS[backoff_idx])
            last = item.last_retried_at or item.created_at
            if now >= last + backoff:
                retryable.append(item)

        return retryable

    def mark_retrying(self, item_id) -> None:
        self.db.query(FailedIngestion).filter(FailedIngestion.id == item_id).update({
            "status": "retrying",
            "retry_count": FailedIngestion.retry_count + 1,
            "last_retried_at": datetime.now(timezone.utc),
        })
        self.db.commit()

    def mark_resolved(self, item_id) -> None:
        self.db.query(FailedIngestion).filter(FailedIngestion.id == item_id).update({
            "status": "resolved",
        })
        self.db.commit()

    def mark_permanently_failed(self, item_id) -> None:
        self.db.query(FailedIngestion).filter(FailedIngestion.id == item_id).update({
            "status": "permanently_failed",
        })
        self.db.commit()

    def expire_old_failures(self) -> int:
        """Mark items that have exceeded max retries as permanently_failed."""
        count = (
            self.db.query(FailedIngestion)
            .filter(
                FailedIngestion.status.in_(["pending", "retrying"]),
                FailedIngestion.retry_count >= MAX_RETRIES,
            )
            .update({"status": "permanently_failed"})
        )
        self.db.commit()
        return count
