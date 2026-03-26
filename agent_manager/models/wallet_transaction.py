"""Wallet transaction log — records every credit movement."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID

from ..database import Base


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, index=True, nullable=False)
    agent_id = Column(String, index=True, nullable=True)
    type = Column(String, index=True, nullable=False)  # subscription_initial / subscription_renewal / usage_deduction / top_up / refund
    amount_cents = Column(Integer, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, nullable=False)  # success / failed
    reference_id = Column(String, nullable=True)
    balance_after_cents = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
