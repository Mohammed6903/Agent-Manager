from __future__ import annotations
import json
import logging
import uuid
from typing import List, Union, TYPE_CHECKING
if TYPE_CHECKING:
    from .agent_service import AgentService

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .secret_service import SecretService
from .integration_client import IntegrationClient
from ..repositories.integration_repository import IntegrationRepository
from ..models.integration import AgentIntegration, IntegrationLog
from ..schemas.integration import AgentIntegrationAssignRequest
from ..integrations import get_integration, list_integrations
from ..integrations.base import BaseIntegration
from ..integrations.google.base_google import BaseGoogleIntegration
from ..integrations.auth import get_auth_handler

logger = logging.getLogger("agent_manager.services.integration_service")

class IntegrationService:
    def __init__(self, db: Session, agent_svc: "AgentService" = None):
        self.db = db
        self.repo = IntegrationRepository(db)
        self.agent_svc = agent_svc

    async def list_available_integrations(self) -> List[dict]:
        """Return a list of all defined integration dicts, with connected agents (name and id)."""
        from collections import defaultdict
        
        # Build a map: integration_name -> list of agent_ids
        assignments = self.repo.get_all_assignments()
        
        # Fetch agent names from AgentService
        agent_names = {}
        if self.agent_svc:
            all_agents = await self.agent_svc.list_agents()
            agent_names = {a["id"]: a["name"] for a in all_agents}
        
        agents_map: dict[str, list] = defaultdict(list)
        for a in assignments:
            agents_map[a.integration_name].append({
                "agent_id": a.agent_id,
                "name": agent_names.get(a.agent_id, "Unknown Agent")
            })
        
        results = []
        for cls in list_integrations():
            d = cls.to_dict()
            d["connected_agents"] = agents_map.get(cls.name, [])
            results.append(d)
        return results

    def get_integration_def(self, name: str) -> dict:
        """Get a single integration definition as a dict."""
        try:
            return get_integration(name).to_dict()
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Integration '{name}' not found.")

    def assign_integration(self, req: AgentIntegrationAssignRequest) -> Union[AgentIntegration, str]:
        try:
            integration_cls = get_integration(req.integration_name)
        except ValueError:
             raise HTTPException(status_code=404, detail=f"Integration '{req.integration_name}' not found.")
        
        # Check auth flow
        from ..integrations.base import AuthFlowType
        if integration_cls.auth_flow != AuthFlowType.STATIC:
            # Do NOT persist the assignment yet — wait for the OAuth callback to succeed.

            if integration_cls.oauth2_provider is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"Integration '{req.integration_name}' declares non-static auth_flow but has no oauth2_provider set."
                )

            auth_url = integration_cls.oauth2_provider.get_auth_url(
                agent_id=req.agent_id,
                integration_name=req.integration_name,
                db=self.db,
            )
            return auth_url

        # STATIC flow
        required_keys = {field.name for field in integration_cls.auth_fields if field.required}
        provided_credentials = req.credentials or {}
        provided_keys = set(provided_credentials.keys())
        
        missing_keys = required_keys - provided_keys
        if missing_keys:
             raise HTTPException(status_code=400, detail=f"Missing required credentials: {missing_keys}")

        # Store credentials in SecretService, keyed by the integration_name
        SecretService.set_secret(self.db, req.agent_id, req.integration_name, provided_credentials)

        # Create mapping in DB
        return self.repo.assign_to_agent(req.agent_id, req.integration_name)

    def unassign_integration(self, agent_id: str, integration_name: str) -> bool:
        """Remove an integration assignment from an agent."""
        removed = self.repo.unassign_from_agent(agent_id, integration_name)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Integration '{integration_name}' is not assigned to agent '{agent_id}'.")
        return True

    def get_agent_integrations(self, agent_id: str) -> List[dict]:
        """List integrations assigned to the agent, returned as dictionaries."""
        assignments = self.repo.get_agent_integrations(agent_id)
        results = []
        for a in assignments:
            try:
                cls = get_integration(a.integration_name)
                d = cls.to_dict()
                d["id"] = str(a.id)
                results.append(d)
            except ValueError:
                # Integration exists in DB but not in code registry
                pass
        return results

    def get_agent_credentials(self, agent_id: str, integration_name: str) -> dict:
        assignment = self.repo.get_assignment(agent_id, integration_name)
        if not assignment:
             raise HTTPException(status_code=404, detail=f"No integration {integration_name} assigned to agent {agent_id}")
             
        creds = SecretService.get_secret(self.db, agent_id, integration_name)
        if not creds:
             raise HTTPException(status_code=404, detail="Credentials not found \u2014 was assignment completed successfully?")
        
        return creds

    def get_client(self, agent_id: str, integration_name: str) -> IntegrationClient:
        """Construct a ready-to-use IntegrationClient for an agent."""
        try:
            integration_cls = get_integration(integration_name)
        except ValueError:
             raise HTTPException(status_code=404, detail=f"Integration '{integration_name}' not found.")

        if issubclass(integration_cls, BaseGoogleIntegration):
             raise HTTPException(status_code=400, detail="Cannot use get_client for Google integrations. They are SDK-based.")

        creds = self.get_agent_credentials(agent_id, integration_name)
        
        auth_handler = get_auth_handler(integration_cls.auth_scheme)
        
        return IntegrationClient(
            db=self.db,
            agent_id=agent_id,
            integration_name=integration_name,
            base_url=integration_cls.base_url,
            endpoints=[{"method": e.method, "path": e.path, "description": e.description} for e in integration_cls.endpoints],
            auth_handler=auth_handler,
            creds=creds
        )

    async def get_unconnected_agents(self, integration_name: str) -> List[dict]:
        """Return agents that are NOT yet connected to the given integration."""
        try:
            get_integration(integration_name)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Integration '{integration_name}' not found.")

        connected_ids = set(self.repo.get_connected_agent_ids(integration_name))

        all_agents = []
        if self.agent_svc:
            all_agents = await self.agent_svc.list_agents()

        return [a for a in all_agents if a["id"] not in connected_ids]

    def get_recent_logs(self, integration_name: str, limit: int = 20) -> List[IntegrationLog]:
        return self.repo.get_recent_logs(integration_name, limit)
