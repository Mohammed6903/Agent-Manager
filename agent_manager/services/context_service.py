import logging
import uuid
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import manual_context_service
from ..repositories.context_repository import ContextRepository
from ..models.context import GlobalContext, AgentContext
from ..schemas.context import GlobalContextCreate, GlobalContextUpdate, AgentContextAssignRequest

logger = logging.getLogger(__name__)


class ContextService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ContextRepository(db)

    def create_global_context(self, req: GlobalContextCreate, org_id: str | None = None) -> GlobalContext:
        existing = self.repo.get_global_context_by_name(req.name, org_id=org_id)
        if existing:
            raise HTTPException(status_code=409, detail=f"Context with name '{req.name}' already exists.")
        ctx = self.repo.create_global_context(req.name, req.content, org_id=org_id)
        # Index into Qdrant for RAG retrieval. Failure is non-fatal — the
        # context still exists in Postgres and can be reindexed later via
        # POST /contexts/{id}/reindex. We do NOT roll back the DB insert
        # on embedding failure because the user's edit shouldn't silently
        # disappear just because an upstream embedding API hiccupped.
        try:
            manual_context_service.index_context(ctx.id, ctx.name, ctx.content)
            ctx.content_hash = manual_context_service.compute_content_hash(ctx.content)
            self.db.commit()
            self.db.refresh(ctx)
        except Exception:
            logger.exception(
                "Failed to index new context %s (%s) — saved but unindexed",
                ctx.id,
                ctx.name,
            )
        return ctx

    def update_global_context(self, context_id: uuid.UUID, req: GlobalContextUpdate) -> GlobalContext:
        if req.name is not None:
            # Fetch the context first to get its org_id for scoped uniqueness check
            existing_ctx = self.repo.get_global_context_by_id(context_id)
            if not existing_ctx:
                raise HTTPException(status_code=404, detail="Context not found.")
            name_conflict = self.repo.get_global_context_by_name(req.name, org_id=existing_ctx.org_id)
            if name_conflict and name_conflict.id != context_id:
                raise HTTPException(status_code=409, detail=f"Context with name '{req.name}' already exists.")
        ctx = self.repo.update_global_context(context_id, name=req.name, content=req.content)
        if not ctx:
            raise HTTPException(status_code=404, detail="Context not found.")

        # Reindex only if content actually changed. Rename-only edits skip
        # the embedding round trip entirely — cheap optimization via hash
        # comparison. If the new hash matches the stored hash, the content
        # is identical to the last successful index and we can skip.
        if req.content is not None:
            new_hash = manual_context_service.compute_content_hash(ctx.content)
            if new_hash != ctx.content_hash:
                try:
                    manual_context_service.reindex_context(ctx.id, ctx.name, ctx.content)
                    ctx.content_hash = new_hash
                    self.db.commit()
                    self.db.refresh(ctx)
                except Exception:
                    logger.exception(
                        "Failed to reindex context %s after update — stored content is current but Qdrant may be stale",
                        ctx.id,
                    )
        return ctx

    def delete_global_context(self, context_id: uuid.UUID):
        # Purge Qdrant chunks BEFORE the DB row goes away. If the Qdrant
        # call fails we still delete the DB row — orphaned chunks with a
        # context_id that no longer exists in Postgres will never match
        # a search (the agent's assigned list won't include them), so
        # they're harmless dead weight that can be cleaned up out-of-band.
        try:
            manual_context_service.delete_context_chunks(context_id)
        except Exception:
            logger.exception(
                "Failed to delete Qdrant chunks for context %s — continuing with DB delete",
                context_id,
            )
        success = self.repo.delete_global_context(context_id)
        if not success:
            raise HTTPException(status_code=404, detail="Context not found.")

    def list_global_contexts(self, org_id: str | None = None) -> List[GlobalContext]:
        return self.repo.list_global_contexts(org_id)

    def get_global_context_by_id(self, context_id: uuid.UUID) -> GlobalContext:
        ctx = self.repo.get_global_context_by_id(context_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Context not found.")
        return ctx

    def get_global_context_by_name(self, name: str, org_id: str | None = None) -> GlobalContext:
        ctx = self.repo.get_global_context_by_name(name, org_id)
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
