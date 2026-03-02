"""Cron ownership SQLAlchemy model."""

from sqlalchemy import Column, String, DateTime, func, ForeignKey, BigInteger, Integer, JSON, Text

from ..database import Base


class CronOwnership(Base):
    __tablename__ = "cron_ownership"

    cron_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    agent_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())


class CronPipelineRun(Base):
    __tablename__ = "cron_pipeline_runs"

    id = Column(String, primary_key=True)           # OpenClaw sessionId / runId
    cron_id = Column(String, ForeignKey("cron_ownership.cron_id", ondelete="CASCADE"), index=True)
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
    created_at = Column(DateTime, default=func.now())
