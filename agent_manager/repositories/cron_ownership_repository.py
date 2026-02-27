"""Cron ownership repository — stores cron_id → user/session/agent mapping in PostgreSQL."""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.cron import CronOwnership

logger = logging.getLogger("agent_manager.repositories.cron_ownership")


class CronOwnershipRepository:
    """Database-backed cron ownership store."""

    def __init__(self, db: Session):
        self.db = db

    def set(self, cron_id: str, user_id: str, session_id: str, agent_id: str):
        """Write/overwrite a cron ownership entry."""
        existing = self.db.query(CronOwnership).filter(CronOwnership.cron_id == cron_id).first()
        if existing:
            existing.user_id = user_id
            existing.session_id = session_id
            existing.agent_id = agent_id
        else:
            entry = CronOwnership(
                cron_id=cron_id,
                user_id=user_id,
                session_id=session_id,
                agent_id=agent_id,
            )
            self.db.add(entry)
        self.db.commit()

    def get(self, cron_id: str) -> Optional[dict]:
        """Fetch a single cron ownership entry."""
        entry = self.db.query(CronOwnership).filter(CronOwnership.cron_id == cron_id).first()
        if not entry:
            return None
        return {
            "user_id": entry.user_id,
            "session_id": entry.session_id,
            "agent_id": entry.agent_id,
        }

    def delete(self, cron_id: str):
        """Remove a cron ownership entry."""
        entry = self.db.query(CronOwnership).filter(CronOwnership.cron_id == cron_id).first()
        if entry:
            self.db.delete(entry)
            self.db.commit()

    def list_all(self) -> Dict[str, dict]:
        """Return the full mapping as {cron_id: {user_id, session_id, agent_id}}."""
        entries = self.db.query(CronOwnership).all()
        return {
            e.cron_id: {
                "user_id": e.user_id,
                "session_id": e.session_id,
                "agent_id": e.agent_id,
            }
            for e in entries
        }

    def list_by_user(self, user_id: str) -> List[dict]:
        """Filter ownership records by user."""
        entries = self.db.query(CronOwnership).filter(CronOwnership.user_id == user_id).all()
        return [
            {
                "job_id": e.cron_id,
                "user_id": e.user_id,
                "session_id": e.session_id,
                "agent_id": e.agent_id,
            }
            for e in entries
        ]

    def list_by_session(self, session_id: str) -> List[dict]:
        """Filter ownership records by session."""
        entries = self.db.query(CronOwnership).filter(CronOwnership.session_id == session_id).all()
        return [
            {
                "job_id": e.cron_id,
                "user_id": e.user_id,
                "session_id": e.session_id,
                "agent_id": e.agent_id,
            }
            for e in entries
        ]

def get_cron_ownership_repository(db: Session) -> CronOwnershipRepository:
    """Dependency injection provider or direct factory for CronOwnershipRepository."""
    return CronOwnershipRepository(db)
