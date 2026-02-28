import uuid
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..repositories.context_repository import ContextRepository
from ..models.context import GlobalContext, AgentContext
from ..schemas.context import GlobalContextCreate, GlobalContextUpdate, AgentContextAssignRequest

class ContextService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ContextRepository(db)

    def create_global_context(self, req: GlobalContextCreate) -> GlobalContext:
        existing = self.repo.get_global_context_by_name(req.name)
        if existing:
            raise HTTPException(status_code=409, detail=f"Context with name '{req.name}' already exists.")
        
        return self.repo.create_global_context(req.name, req.content)

    def update_global_context(self, context_id: uuid.UUID, req: GlobalContextUpdate) -> GlobalContext:
        if req.name is not None:
             existing = self.repo.get_global_context_by_name(req.name)
             if existing and existing.id != context_id:
                  raise HTTPException(status_code=409, detail=f"Context with name '{req.name}' already exists.")

        ctx = self.repo.update_global_context(context_id, name=req.name, content=req.content)
        if not ctx:
             raise HTTPException(status_code=404, detail="Context not found.")
        return ctx

    def delete_global_context(self, context_id: uuid.UUID):
        success = self.repo.delete_global_context(context_id)
        if not success:
            raise HTTPException(status_code=404, detail="Context not found.")

    def list_global_contexts(self) -> List[GlobalContext]:
        return self.repo.list_global_contexts()

    def get_global_context_by_id(self, context_id: uuid.UUID) -> GlobalContext:
        ctx = self.repo.get_global_context_by_id(context_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Context not found.")
        return ctx

    def get_global_context_by_name(self, name: str) -> GlobalContext:
        ctx = self.repo.get_global_context_by_name(name)
        if not ctx:
            raise HTTPException(status_code=404, detail="Context not found.")
        return ctx

    def assign_context(self, req: AgentContextAssignRequest) -> AgentContext:
        try:
           ctx_uuid = uuid.UUID(req.context_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID for context_id.")
            
        context = self.get_global_context_by_id(ctx_uuid)
        return self.repo.assign_context_to_agent(req.agent_id, context.id)

    def unassign_context(self, agent_id: str, context_id: uuid.UUID):
        success = self.repo.unassign_context_from_agent(agent_id, context_id)
        if not success:
            raise HTTPException(status_code=404, detail="Assignment not found.")

    def get_available_contexts_for_agent(self, agent_id: str) -> List[GlobalContext]:
        # returns full contexts for the complete list response
        return self.repo.get_assigned_contexts_for_agent(agent_id)
        
    def get_context_content_for_agent(self, agent_id: str, context_id: uuid.UUID) -> str:
        # Ensure it's actually assigned to the agent
        contexts = self.repo.get_assigned_contexts_for_agent(agent_id)
        target = next((ctx for ctx in contexts if ctx.id == context_id), None)
        
        if not target:
            raise HTTPException(status_code=403, detail=f"Context '{context_id}' is not assigned to agent '{agent_id}'")
            
        return target.content
