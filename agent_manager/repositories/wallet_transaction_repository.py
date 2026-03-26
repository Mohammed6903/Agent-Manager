# repositories/wallet_transaction_repository.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.wallet_transaction import WalletTransaction


class WalletTransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: str,
        agent_id: str | None,
        type: str,
        amount_cents: int,
        description: str,
        status: str,
        balance_after_cents: int | None = None,
        reference_id: str | None = None,
    ) -> WalletTransaction:
        entry = WalletTransaction(
            user_id=user_id,
            agent_id=agent_id,
            type=type,
            amount_cents=amount_cents,
            description=description,
            status=status,
            balance_after_cents=balance_after_cents,
            reference_id=reference_id,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_by_user(
        self, user_id: str, limit: int = 50, offset: int = 0, type_filter: str | None = None,
    ) -> List[WalletTransaction]:
        q = self.db.query(WalletTransaction).filter(WalletTransaction.user_id == user_id)
        if type_filter:
            q = q.filter(WalletTransaction.type == type_filter)
        return q.order_by(WalletTransaction.created_at.desc()).offset(offset).limit(limit).all()

    def list_by_agent(self, agent_id: str) -> List[WalletTransaction]:
        return (
            self.db.query(WalletTransaction)
            .filter(WalletTransaction.agent_id == agent_id)
            .order_by(WalletTransaction.created_at.desc())
            .all()
        )
