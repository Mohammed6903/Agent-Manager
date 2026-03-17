# repositories/agent_registry_repository.py
from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.agent_registry import AgentRegistry


class AgentRegistryRepository:
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
    ) -> AgentRegistry:
        entry = AgentRegistry(
            agent_id=agent_id,
            name=name,
            workspace=workspace,
            agent_dir=agent_dir,
            org_id=org_id,
            user_id=user_id,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get(self, agent_id: str, org_id: str | None = None) -> AgentRegistry | None:
        q = self.db.query(AgentRegistry).filter(AgentRegistry.agent_id == agent_id)
        if org_id is not None:
            q = q.filter(AgentRegistry.org_id == org_id)
        return q.first()

    def list(self, org_id: str | None = None) -> List[AgentRegistry]:
        q = self.db.query(AgentRegistry)
        if org_id is not None:
            q = q.filter(AgentRegistry.org_id == org_id)
        return q.order_by(AgentRegistry.created_at.desc()).all()

    def update_name(self, agent_id: str, name: str) -> None:
        self.db.query(AgentRegistry).filter(
            AgentRegistry.agent_id == agent_id
        ).update({"name": name})
        self.db.commit()

    def delete(self, agent_id: str) -> None:
        self.db.query(AgentRegistry).filter(
            AgentRegistry.agent_id == agent_id
        ).delete()
        self.db.commit()