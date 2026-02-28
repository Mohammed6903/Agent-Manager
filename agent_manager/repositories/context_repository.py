import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound

from ..models.context import GlobalContext, AgentContext

class ContextRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_global_context(self, name: str, content: str) -> GlobalContext:
        ctx = GlobalContext(name=name, content=content)
        self.db.add(ctx)
        self.db.commit()
        self.db.refresh(ctx)
        return ctx

    def update_global_context(self, context_id: uuid.UUID, name: Optional[str] = None, content: Optional[str] = None) -> Optional[GlobalContext]:
        ctx = self.get_global_context_by_id(context_id)
        if not ctx:
            return None
            
        if name is not None:
            ctx.name = name
        if content is not None:
            ctx.content = content
            
        self.db.commit()
        self.db.refresh(ctx)
        return ctx
        
    def delete_global_context(self, context_id: uuid.UUID) -> bool:
        ctx = self.get_global_context_by_id(context_id)
        if ctx:
            self.db.delete(ctx)
            self.db.commit()
            return True
        return False

    def get_global_context_by_id(self, context_id: uuid.UUID) -> Optional[GlobalContext]:
        return self.db.execute(
            select(GlobalContext).where(GlobalContext.id == context_id)
        ).scalar_one_or_none()

    def get_global_context_by_name(self, name: str) -> Optional[GlobalContext]:
        return self.db.execute(
            select(GlobalContext).where(GlobalContext.name == name)
        ).scalar_one_or_none()

    def list_global_contexts(self) -> List[GlobalContext]:
        return list(self.db.execute(select(GlobalContext)).scalars().all())

    def assign_context_to_agent(self, agent_id: str, context_id: uuid.UUID) -> AgentContext:
        # Check if already assigned
        existing = self.db.execute(
            select(AgentContext).where(
                AgentContext.agent_id == agent_id,
                AgentContext.context_id == context_id
            )
        ).scalar_one_or_none()
        
        if existing:
            return existing
            
        mapping = AgentContext(agent_id=agent_id, context_id=context_id)
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        return mapping

    def get_assigned_contexts_for_agent(self, agent_id: str) -> List[GlobalContext]:
        stmt = (
            select(GlobalContext)
            .join(AgentContext, AgentContext.context_id == GlobalContext.id)
            .where(AgentContext.agent_id == agent_id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def unassign_context_from_agent(self, agent_id: str, context_id: uuid.UUID) -> bool:
        mapping = self.db.execute(
            select(AgentContext).where(
                AgentContext.agent_id == agent_id,
                AgentContext.context_id == context_id
            )
        ).scalar_one_or_none()
        
        if mapping:
            self.db.delete(mapping)
            self.db.commit()
            return True
        return False
