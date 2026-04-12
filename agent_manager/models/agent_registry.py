"""Agent registry — fast local cache of agent metadata with org scoping."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from ..database import Base


# Agent type enum. Stored as a plain string to keep migrations simple.
# Consumers should compare against these module-level constants instead
# of hardcoding the string literals so a future rename is grep-able.
AGENT_TYPE_DEFAULT = "default"
AGENT_TYPE_QA = "qa"
AGENT_TYPE_VOICE = "voice"
AGENT_TYPES = (AGENT_TYPE_DEFAULT, AGENT_TYPE_QA, AGENT_TYPE_VOICE)


class AgentRegistry(Base):
    __tablename__ = "agent_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    org_id = Column(String, index=True, nullable=True)   # None = unscoped / legacy
    user_id = Column(String, index=True, nullable=True)  # who created it
    workspace = Column(String, nullable=True)
    agent_dir = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    # Soft-delete timestamp. NULL = active. When set, the row is hidden
    # from list/get queries by default but kept in the DB so the agent
    # can be restored later (see AgentRegistryRepository.restore).
    # This decouples visibility from the subscription/billing model —
    # soft-delete works identically whether ENFORCE_AGENT_SUBSCRIPTION
    # is on or off.
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # ── Agent type + Q&A config ─────────────────────────────────────────
    # ``agent_type`` is one of ``AGENT_TYPES``. Controls which code paths
    # an agent participates in: Default is the historical full-featured
    # chat agent; Q&A is a locked-down public-facing assistant reachable
    # by unauthenticated visitors via /api/public/qa/{agent_id}; Voice
    # is currently just a label (voice-specific behavior is deferred to
    # a later pass). Existing rows get backfilled to "default" by the
    # migration so current behavior is preserved.
    agent_type = Column(
        String,
        nullable=False,
        default=AGENT_TYPE_DEFAULT,
        server_default=AGENT_TYPE_DEFAULT,
    )

    # Q&A-specific config fields. All nullable — only meaningful when
    # agent_type == "qa". None of these leak to the browser except
    # through the GET /info endpoint, which explicitly excludes
    # ``qa_persona_instructions`` (that field stays server-side and
    # is baked into the guardian system prompt at chat time).
    qa_welcome_message = Column(Text, nullable=True)
    qa_persona_instructions = Column(Text, nullable=True)
    qa_page_title = Column(String(200), nullable=True)
    qa_page_subtitle = Column(String(500), nullable=True)

    __table_args__ = (
        # Most common query: all agents for a given org
        Index("ix_agent_registry_org_id_agent_id", "org_id", "agent_id"),
    )