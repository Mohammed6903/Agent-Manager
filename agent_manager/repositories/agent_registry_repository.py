# repositories/agent_registry_repository.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.agent_registry import AgentRegistry


class AgentRegistryRepository:
    """CRUD + soft-delete access to the ``agent_registry`` table.

    Soft-delete semantics: setting ``deleted_at`` hides the row from
    ``list`` and ``get`` by default. Pass ``include_deleted=True`` to
    bypass the filter (admin tools, restore flows). ``delete`` (hard
    delete) remains available but should be reserved for true purges —
    normal user-facing deletes go through ``soft_delete`` so the row
    can be restored via ``restore``.
    """

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        agent_id: str,
        name: str,
        workspace: str,
        agent_dir: str,
        org_id: str | None = None,
        user_id: str | None = None,
        agent_type: str | None = None,
        qa_welcome_message: str | None = None,
        qa_persona_instructions: str | None = None,
        qa_page_title: str | None = None,
        qa_page_subtitle: str | None = None,
        llm_model: str | None = None,
    ) -> AgentRegistry:
        # agent_type is stored as-is; None lets the model's server_default
        # ("default") fill in for us at insert time.
        kwargs: dict = dict(
            agent_id=agent_id,
            name=name,
            workspace=workspace,
            agent_dir=agent_dir,
            org_id=org_id,
            user_id=user_id,
            qa_welcome_message=qa_welcome_message,
            qa_persona_instructions=qa_persona_instructions,
            qa_page_title=qa_page_title,
            qa_page_subtitle=qa_page_subtitle,
            llm_model=llm_model,
        )
        if agent_type is not None:
            kwargs["agent_type"] = agent_type
        entry = AgentRegistry(**kwargs)
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def update_qa_config(
        self,
        agent_id: str,
        agent_type: str | None = None,
        qa_welcome_message: str | None = None,
        qa_persona_instructions: str | None = None,
        qa_page_title: str | None = None,
        qa_page_subtitle: str | None = None,
    ) -> bool:
        """Update type + Q&A config fields on an existing agent.

        Only fields passed as non-None are written — passing None means
        "don't touch this column." Returns True if a row was updated.
        Callers should verify ownership via ``get()`` before calling.
        """
        updates: dict = {}
        if agent_type is not None:
            updates["agent_type"] = agent_type
        if qa_welcome_message is not None:
            updates["qa_welcome_message"] = qa_welcome_message
        if qa_persona_instructions is not None:
            updates["qa_persona_instructions"] = qa_persona_instructions
        if qa_page_title is not None:
            updates["qa_page_title"] = qa_page_title
        if qa_page_subtitle is not None:
            updates["qa_page_subtitle"] = qa_page_subtitle
        if not updates:
            return False
        count = (
            self.db.query(AgentRegistry)
            .filter(AgentRegistry.agent_id == agent_id)
            .update(updates)
        )
        self.db.commit()
        return count > 0

    def get(
        self,
        agent_id: str,
        org_id: str | None = None,
        user_id: str | None = None,
        include_deleted: bool = False,
    ) -> AgentRegistry | None:
        q = self.db.query(AgentRegistry).filter(AgentRegistry.agent_id == agent_id)
        if org_id is not None:
            q = q.filter(AgentRegistry.org_id == org_id)
        if user_id is not None:
            q = q.filter(AgentRegistry.user_id == user_id)
        if not include_deleted:
            q = q.filter(AgentRegistry.deleted_at.is_(None))
        return q.first()

    def list(
        self,
        org_id: str | None = None,
        user_id: str | None = None,
        include_deleted: bool = False,
    ) -> List[AgentRegistry]:
        q = self.db.query(AgentRegistry)
        if org_id is not None:
            q = q.filter(AgentRegistry.org_id == org_id)
        if user_id is not None:
            q = q.filter(AgentRegistry.user_id == user_id)
        if not include_deleted:
            q = q.filter(AgentRegistry.deleted_at.is_(None))
        return q.order_by(AgentRegistry.created_at.desc()).all()

    def update_name(self, agent_id: str, name: str) -> None:
        self.db.query(AgentRegistry).filter(
            AgentRegistry.agent_id == agent_id
        ).update({"name": name})
        self.db.commit()

    def soft_delete(self, agent_id: str) -> bool:
        """Mark the agent as deleted by stamping ``deleted_at``.

        Returns True if a row was updated, False if the agent_id
        wasn't found (or was already soft-deleted — idempotent).
        """
        now = datetime.now(timezone.utc)
        count = (
            self.db.query(AgentRegistry)
            .filter(
                AgentRegistry.agent_id == agent_id,
                AgentRegistry.deleted_at.is_(None),
            )
            .update({"deleted_at": now})
        )
        self.db.commit()
        return count > 0

    def restore(self, agent_id: str) -> bool:
        """Clear ``deleted_at`` so the agent is visible again.

        Returns True if a row was updated. Idempotent — restoring an
        already-active agent returns False but doesn't raise.
        """
        count = (
            self.db.query(AgentRegistry)
            .filter(
                AgentRegistry.agent_id == agent_id,
                AgentRegistry.deleted_at.isnot(None),
            )
            .update({"deleted_at": None})
        )
        self.db.commit()
        return count > 0

    def delete(self, agent_id: str) -> None:
        """Hard-delete the registry row (purge, not recoverable).

        Prefer ``soft_delete`` for user-facing deletes. This exists for
        admin/purge flows that want the row actually gone from the DB.
        """
        self.db.query(AgentRegistry).filter(
            AgentRegistry.agent_id == agent_id
        ).delete()
        self.db.commit()