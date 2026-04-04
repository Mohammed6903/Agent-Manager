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

    async def list_available_integrations(self, org_id: str | None = None) -> List[dict]:
        """Return a list of all defined integration dicts, with connected agents (name and id)."""
        from collections import defaultdict
        
        # Build a map: integration_name -> list of agent_ids
        assignments = self.repo.get_all_assignments()
        
        # Fetch agent names from AgentService
        agent_names = {}
        if self.agent_svc:
            all_agents = await self.agent_svc.list_agents(org_id=org_id)
            agent_names = {a["id"]: a["name"] for a in all_agents}
        
        agents_map: dict[str, list] = defaultdict(list)
        for a in assignments:
            agents_map[a.integration_name].append({
                "agent_id": a.agent_id,
                "name": agent_names.get(a.agent_id, "Unknown Agent"),
                "display_metadata": a.integration_metadata,
            })
        
        results = []
        for cls in list_integrations():
            d = cls.to_dict()
            raw_agents = agents_map.get(cls.name, [])
            d["connected_agents"] = [
                {
                    "agent_id": a["agent_id"],
                    "name": a["name"],
                    "display_metadata": cls.filter_metadata(a["display_metadata"]),
                }
                for a in raw_agents
            ]
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
        result = self.repo.assign_to_agent(req.agent_id, req.integration_name)

        from .agent_activity_service import log_activity_sync
        log_activity_sync(self.db, req.agent_id, "integration_connected",
            f"Connected {req.integration_name}",
            metadata={"integration": req.integration_name})

        return result

    def unassign_integration(self, agent_id: str, integration_name: str) -> bool:
        """Remove an integration assignment from an agent, including stored credentials."""
        removed = self.repo.unassign_from_agent(agent_id, integration_name)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Integration '{integration_name}' is not assigned to agent '{agent_id}'.")
        # Delete the stored credentials — no longer needed once unassigned
        SecretService.delete_secret(self.db, agent_id, integration_name)

        from .agent_activity_service import log_activity_sync
        log_activity_sync(self.db, agent_id, "integration_disconnected",
            f"Disconnected {integration_name}",
            metadata={"integration": integration_name})

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
                d["display_metadata"] = cls.filter_metadata(a.integration_metadata)
                results.append(d)
            except ValueError:
                # Integration exists in DB but not in code registry
                pass
        return results

    def get_agent_integrations_status(self, agent_id: str) -> dict:
        """Return connected and available integrations for a given agent."""
        assignments = self.repo.get_agent_integrations(agent_id)
        connected_names = set()
        connected = []
        for a in assignments:
            try:
                cls = get_integration(a.integration_name)
                d = cls.to_dict()
                d["id"] = str(a.id)
                d["display_metadata"] = cls.filter_metadata(a.integration_metadata)
                connected.append(d)
                connected_names.add(a.integration_name)
            except ValueError:
                pass

        available = []
        for cls in list_integrations():
            if cls.name not in connected_names:
                available.append(cls.to_dict())

        return {"connected": connected, "available": available}

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

    async def get_unconnected_agents(self, integration_name: str, org_id: str | None = None) -> List[dict]:
        """Return agents that are NOT yet connected to the given integration."""
        try:
            get_integration(integration_name)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Integration '{integration_name}' not found.")

        connected_ids = set(self.repo.get_connected_agent_ids(integration_name))

        all_agents = []
        if self.agent_svc:
            all_agents = await self.agent_svc.list_agents(org_id=org_id)

        return [a for a in all_agents if a["id"] not in connected_ids]

    def get_recent_logs(self, integration_name: str, limit: int = 20) -> List[IntegrationLog]:
        return self.repo.get_recent_logs(integration_name, limit)

    async def test_connection(self, agent_id: str, integration_name: str) -> dict:
        """Make a lightweight API call to verify the integration credentials are valid."""
        try:
            integration_cls = get_integration(integration_name, allow_inactive=True)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Integration '{integration_name}' not found.")

        assignment = self.repo.get_assignment(agent_id, integration_name)
        if not assignment:
            raise HTTPException(status_code=404, detail=f"Integration '{integration_name}' not assigned to agent.")

        test_config = getattr(integration_cls, "test_connection", None)
        if not test_config:
            return {"status": "unsupported", "message": "Test not available for this integration."}

        method, path = test_config

        # Google SDK integrations need special handling
        if issubclass(integration_cls, BaseGoogleIntegration):
            try:
                from ..integrations.google.gmail.auth_service import get_valid_credentials
                import httpx
                creds = get_valid_credentials(self.db, agent_id)
                if not creds:
                    return {"status": "failed", "message": "Credentials expired or missing. Re-authorize required."}
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://www.googleapis.com/{path}",
                        headers={"Authorization": f"Bearer {creds.token}"},
                        timeout=10.0,
                    )
                if resp.status_code < 400:
                    return {"status": "ok", "message": "Connection verified."}
                else:
                    return {"status": "failed", "message": f"API returned {resp.status_code}."}
            except Exception as e:
                return {"status": "failed", "message": str(e)}

        # SDK integrations (Twitter, LinkedIn) — use stored credentials directly
        from ..integrations.base import BaseSDKIntegration
        if issubclass(integration_cls, BaseSDKIntegration):
            try:
                import httpx
                creds = SecretService.get_secret(self.db, agent_id, integration_name)
                if not creds or not creds.get("access_token"):
                    return {"status": "failed", "message": "Credentials expired or missing. Re-authorize required."}
                url = f"{integration_cls.base_url}{path}" if not path.startswith("http") else path
                async with httpx.AsyncClient() as http:
                    resp = await http.request(
                        method, url,
                        headers={"Authorization": f"Bearer {creds['access_token']}"},
                        timeout=10.0,
                    )
                if resp.status_code < 400:
                    return {"status": "ok", "message": "Connection verified."}
                else:
                    return {"status": "failed", "message": f"API returned {resp.status_code}."}
            except Exception as e:
                return {"status": "failed", "message": str(e)}

        # HTTP integrations — use IntegrationClient
        try:
            client = self.get_client(agent_id, integration_name)
            async with client:
                resp = await client.request(method, f"{client.base_url}{path}")
            if resp.status_code < 400:
                return {"status": "ok", "message": "Connection verified."}
            else:
                return {"status": "failed", "message": f"API returned {resp.status_code}."}
        except Exception as e:
            return {"status": "failed", "message": str(e)}
