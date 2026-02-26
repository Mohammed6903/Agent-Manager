"""Cron ownership SQLAlchemy model."""

from sqlalchemy import Column, String, DateTime, func

from ..database import Base


class CronOwnership(Base):
    __tablename__ = "cron_ownership"

    cron_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
