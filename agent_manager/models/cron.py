"""Cron ownership SQLAlchemy model."""

from sqlalchemy import Boolean, Column, String, DateTime, func, ForeignKey, BigInteger, Integer, JSON, Text, Float

from ..database import Base


class CronOwnership(Base):
    __tablename__ = "cron_ownership"

    cron_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    # Reason the cron was auto-disabled, if any. NULL means the cron's
    # current enabled state was set by the user explicitly — we must
    # not touch it. Currently the only value we write is
    # "balance_negative" (user's wallet dropped below the minimum), but
    # the field is a free-form string so new auto-disable reasons can
    # be added later without a migration.
    disabled_reason = Column(String, nullable=True)


class CronPipelineRun(Base):
    __tablename__ = "cron_pipeline_runs"

    id = Column(String, primary_key=True)           # OpenClaw sessionId / runId
    cron_id = Column(String, ForeignKey("cron_ownership.cron_id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String)                         # success | partial | error
    started_at = Column(BigInteger)                 # epoch ms
    finished_at = Column(BigInteger)
    duration_ms = Column(Integer)
    tasks = Column(JSON)                            # final tasks array from agent
    global_integrations = Column(JSON, default=list)
    global_context_sources = Column(JSON, default=list)
    raw_summary = Column(Text)                      # full agent response
    summary = Column(Text, nullable=True)             # agent-generated problem summary for the user
    model = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    input_cost = Column(Float, default=0.0)
    output_cost = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    billed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now())
