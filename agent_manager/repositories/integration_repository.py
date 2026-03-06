import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.integration import AgentIntegration, IntegrationLog


class IntegrationRepository:
    def __init__(self, db: Session):
        self.db = db

    # -- Agent Integration --

    def assign_to_agent(self, agent_id: str, integration_name: str) -> AgentIntegration:
        existing = self.db.execute(
            select(AgentIntegration).where(
                AgentIntegration.agent_id == agent_id,
                AgentIntegration.integration_name == integration_name
            )
        ).scalar_one_or_none()
        
        if existing:
            return existing
            
        mapping = AgentIntegration(agent_id=agent_id, integration_name=integration_name)
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        return mapping

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
            return True
        return False

    def get_all_assignments(self) -> List[AgentIntegration]:
        """Return every agent-integration assignment row."""
        return list(self.db.execute(select(AgentIntegration)).scalars().all())

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
