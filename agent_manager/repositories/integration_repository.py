import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clients.plugin_notifier import notify_plugin_integration_change
from ..models.integration import AgentIntegration, IntegrationLog


class IntegrationRepository:
    def __init__(self, db: Session):
        self.db = db

    # -- Agent Integration --

    def assign_to_agent(self, agent_id: str, integration_name: str, metadata: dict = None) -> AgentIntegration:
        existing = self.db.execute(
            select(AgentIntegration).where(
                AgentIntegration.agent_id == agent_id,
                AgentIntegration.integration_name == integration_name
            )
        ).scalar_one_or_none()
        
        if existing:
            if metadata is not None:
                existing.integration_metadata = metadata
                self.db.commit()
                self.db.refresh(existing)
            return existing

        mapping = AgentIntegration(
            agent_id=agent_id,
            integration_name=integration_name,
            integration_metadata=metadata,
        )
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        notify_plugin_integration_change(agent_id)
        return mapping

    def update_metadata(self, agent_id: str, integration_name: str, metadata: dict) -> Optional[AgentIntegration]:
        """Update (or set) the integration_metadata for an existing assignment."""
        assignment = self.get_assignment(agent_id, integration_name)
        if not assignment:
            return None
        assignment.integration_metadata = metadata
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def get_assignment(self, agent_id: str, integration_name: str) -> Optional[AgentIntegration]:
        return self.db.execute(
            select(AgentIntegration).where(
                AgentIntegration.agent_id == agent_id,
                AgentIntegration.integration_name == integration_name
            )
        ).scalar_one_or_none()

    def get_agent_integrations(self, agent_id: str) -> List[AgentIntegration]:
        stmt = select(AgentIntegration).where(AgentIntegration.agent_id == agent_id)
        return list(self.db.execute(stmt).scalars().all())

    def unassign_from_agent(self, agent_id: str, integration_name: str) -> bool:
        mapping = self.db.execute(
            select(AgentIntegration).where(
                AgentIntegration.agent_id == agent_id,
                AgentIntegration.integration_name == integration_name
            )
        ).scalar_one_or_none()
        
        if mapping:
            self.db.delete(mapping)
            self.db.commit()
            notify_plugin_integration_change(agent_id)
            return True
        return False

    def get_all_assignments(self) -> List[AgentIntegration]:
        """Return every agent-integration assignment row."""
        return list(self.db.execute(select(AgentIntegration)).scalars().all())

    def get_connected_agent_ids(self, integration_name: str) -> List[str]:
        """Return agent IDs that are already connected to the given integration."""
        stmt = select(AgentIntegration.agent_id).where(
            AgentIntegration.integration_name == integration_name
        )
        return [row for row in self.db.execute(stmt).scalars().all()]

    def delete_all_for_agent(self, agent_id: str) -> None:
        """Delete integration assignments for an agent.

        IntegrationLog rows are intentionally preserved for analytics and
        usage auditing — they must never be deleted when an agent is removed.
        """
        from sqlalchemy import delete as sa_delete
        self.db.execute(
            sa_delete(AgentIntegration).where(AgentIntegration.agent_id == agent_id)
        )
        self.db.commit()
        notify_plugin_integration_change(agent_id)

    def create_log(self, integration_name: str, agent_id: str, method: str, endpoint: str, status_code: int, duration_ms: int, request_id: Optional[str] = None, error_message: Optional[str] = None) -> IntegrationLog:
        log = IntegrationLog(
            integration_name=integration_name,
            agent_id=agent_id,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            duration_ms=duration_ms,
            request_id=request_id,
            error_message=error_message
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def get_recent_logs(self, integration_name: str, limit: int = 20) -> List[IntegrationLog]:
        return list(
            self.db.execute(
                select(IntegrationLog)
                .where(IntegrationLog.integration_name == integration_name)
                .order_by(IntegrationLog.created_at.desc())
                .limit(limit)
            ).scalars().all()
        )
