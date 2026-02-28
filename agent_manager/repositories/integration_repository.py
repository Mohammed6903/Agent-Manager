import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.integration import GlobalIntegration, AgentIntegration, IntegrationLog


class IntegrationRepository:
    def __init__(self, db: Session):
        self.db = db

    # -- Global Integration --

    def create_global_integration(self, name: str, type: str, status: str, base_url: str, auth_scheme: dict, auth_fields: list, endpoints: list, usage_instructions: str) -> GlobalIntegration:
        integration = GlobalIntegration(
            name=name,
            type=type,
            status=status,
            base_url=base_url,
            auth_scheme=auth_scheme,
            auth_fields=auth_fields,
            endpoints=endpoints,
            usage_instructions=usage_instructions
        )
        self.db.add(integration)
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def update_global_integration(self, integration_id: uuid.UUID, **kwargs) -> Optional[GlobalIntegration]:
        integration = self.get_global_integration(integration_id)
        if not integration:
            return None
            
        for key, value in kwargs.items():
            if value is not None:
                setattr(integration, key, value)
                
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def get_global_integration(self, integration_id: uuid.UUID) -> Optional[GlobalIntegration]:
        return self.db.execute(select(GlobalIntegration).where(GlobalIntegration.id == integration_id)).scalar_one_or_none()

    def get_global_integration_by_name(self, name: str) -> Optional[GlobalIntegration]:
        return self.db.execute(select(GlobalIntegration).where(GlobalIntegration.name == name)).scalar_one_or_none()

    def list_global_integrations(self) -> List[GlobalIntegration]:
        return list(self.db.execute(select(GlobalIntegration)).scalars().all())

    def delete_global_integration(self, integration_id: uuid.UUID) -> bool:
        integration = self.get_global_integration(integration_id)
        if integration:
            self.db.delete(integration)
            self.db.commit()
            return True
        return False

    # -- Agent Integration --

    def assign_to_agent(self, agent_id: str, integration_id: uuid.UUID) -> AgentIntegration:
        existing = self.db.execute(
            select(AgentIntegration).where(
                AgentIntegration.agent_id == agent_id,
                AgentIntegration.integration_id == integration_id
            )
        ).scalar_one_or_none()
        
        if existing:
            return existing
            
        mapping = AgentIntegration(agent_id=agent_id, integration_id=integration_id)
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        return mapping

    def get_assignment(self, agent_id: str, integration_id: uuid.UUID) -> Optional[AgentIntegration]:
        return self.db.execute(
            select(AgentIntegration).where(
                AgentIntegration.agent_id == agent_id,
                AgentIntegration.integration_id == integration_id
            )
        ).scalar_one_or_none()

    def get_agent_integrations(self, agent_id: str) -> List[GlobalIntegration]:
        stmt = (
            select(GlobalIntegration)
            .join(AgentIntegration, AgentIntegration.integration_id == GlobalIntegration.id)
            .where(AgentIntegration.agent_id == agent_id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def unassign_from_agent(self, agent_id: str, integration_id: uuid.UUID) -> bool:
        mapping = self.db.execute(
            select(AgentIntegration).where(
                AgentIntegration.agent_id == agent_id,
                AgentIntegration.integration_id == integration_id
            )
        ).scalar_one_or_none()
        
        if mapping:
            self.db.delete(mapping)
            self.db.commit()
            return True
        return False

    # -- Logs --

    def get_recent_logs(self, integration_id: uuid.UUID, limit: int = 20) -> List[IntegrationLog]:
        return list(
            self.db.execute(
                select(IntegrationLog)
                .where(IntegrationLog.integration_id == integration_id)
                .order_by(IntegrationLog.created_at.desc())
                .limit(limit)
            ).scalars().all()
        )
