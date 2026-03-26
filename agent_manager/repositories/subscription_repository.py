# repositories/subscription_repository.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models.agent_subscription import AgentSubscription


class SubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        agent_id: str,
        org_id: str,
        user_id: str,
        amount_cents: int,
        next_billing_date: datetime,
    ) -> AgentSubscription:
        entry = AgentSubscription(
            agent_id=agent_id,
            org_id=org_id,
            user_id=user_id,
            amount_cents=amount_cents,
            next_billing_date=next_billing_date,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get_by_agent_id(self, agent_id: str) -> Optional[AgentSubscription]:
        return (
            self.db.query(AgentSubscription)
            .filter(AgentSubscription.agent_id == agent_id)
            .first()
        )

    def list_by_org(
        self, org_id: str, include_deleted: bool = False
    ) -> List[AgentSubscription]:
        q = self.db.query(AgentSubscription).filter(
            AgentSubscription.org_id == org_id
        )
        if not include_deleted:
            q = q.filter(AgentSubscription.status != "deleted")
        return q.order_by(AgentSubscription.created_at.desc()).all()

    def list_by_user(
        self, user_id: str, include_deleted: bool = False
    ) -> List[AgentSubscription]:
        q = self.db.query(AgentSubscription).filter(
            AgentSubscription.user_id == user_id
        )
        if not include_deleted:
            q = q.filter(AgentSubscription.status != "deleted")
        return q.order_by(AgentSubscription.created_at.desc()).all()

    def list_due_for_renewal(self, as_of: datetime) -> List[AgentSubscription]:
        """SELECT ... FOR UPDATE to prevent double-charging on concurrent workers."""
        return (
            self.db.query(AgentSubscription)
            .filter(
                AgentSubscription.status == "active",
                AgentSubscription.next_billing_date <= as_of,
            )
            .with_for_update(skip_locked=True)
            .all()
        )

    def list_locked_for_deletion(self, as_of: datetime) -> List[AgentSubscription]:
        """SELECT ... FOR UPDATE to prevent duplicate soft-deletes."""
        cutoff = as_of - timedelta(days=settings.SUBSCRIPTION_DELETE_AFTER_DAYS)
        return (
            self.db.query(AgentSubscription)
            .filter(
                AgentSubscription.status == "locked",
                AgentSubscription.locked_at <= cutoff,
            )
            .with_for_update(skip_locked=True)
            .all()
        )

    def update_status(self, agent_id: str, status: str, **kwargs) -> None:
        updates = {"status": status, **kwargs}
        self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent_id
        ).update(updates)
        self.db.commit()

    def mark_renewed(self, agent_id: str, new_next_billing_date: datetime) -> None:
        self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent_id
        ).update({
            "next_billing_date": new_next_billing_date,
            "status": "active",
        })
        self.db.commit()

    def lock(self, agent_id: str) -> None:
        now = datetime.now(timezone.utc)
        self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent_id
        ).update({"status": "locked", "locked_at": now})
        self.db.commit()

    def soft_delete(self, agent_id: str) -> None:
        now = datetime.now(timezone.utc)
        self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent_id
        ).update({"status": "deleted", "deleted_at": now})
        self.db.commit()

    def cancel(self, agent_id: str) -> None:
        now = datetime.now(timezone.utc)
        self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent_id
        ).update({"status": "deleted", "deleted_at": now})
        self.db.commit()

    def unlock(self, agent_id: str, new_next_billing_date: datetime) -> None:
        self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent_id
        ).update({
            "status": "active",
            "locked_at": None,
            "next_billing_date": new_next_billing_date,
        })
        self.db.commit()
