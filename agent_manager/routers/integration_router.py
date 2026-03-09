from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Response, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.integration import (
    IntegrationDefResponse,
    AgentIntegrationAssignRequest,
    AgentIntegrationResponse,
    AgentIntegrationListResponse,
    AgentIntegrationsStatusResponse,
    AgentAssignedIntegrationDetail,
    IntegrationDefBriefResponse,
    IntegrationLogListResponse,
)
from ..dependencies import get_db, get_agent_service
from ..services.agent_service import AgentService
from ..services.integration_service import IntegrationService

router = APIRouter(tags=["Integration Management"])

def get_integration_service(
    db: Session = Depends(get_db),
    agent_svc: AgentService = Depends(get_agent_service)
) -> IntegrationService:
    return IntegrationService(db, agent_svc)

# -- Global Definitions --

@router.get("", response_model=List[IntegrationDefResponse])
async def list_available_integrations(
    svc: IntegrationService = Depends(get_integration_service),
):
    """List all available hardcoded integrations."""
    return await svc.list_available_integrations()

@router.get("/{integration_name}", response_model=IntegrationDefResponse)
async def get_integration_def(
    integration_name: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Get a specific integration definition."""
    # Note: though get_integration_def is currently sync in service, 
    # we make this async for consistency if it ever needs to fetch agents.
    # For now, we can just return it.
    return svc.get_integration_def(integration_name)


# -- Agent Assignment & Usage --

@router.post("/assign")
def assign_integration_to_agent(
    req: AgentIntegrationAssignRequest,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Assign an integration to an agent by providing valid credentials."""
    result = svc.assign_integration(req)
    
    if isinstance(result, str):
        # result is an auth_url string for OAuth flows — return it as JSON
        return {"status": "oauth_required", "auth_url": result, "integration_name": req.integration_name, "agent_id": req.agent_id}

    return AgentIntegrationResponse.model_validate(result)

@router.get("/oauth/callback/{provider}")
async def generic_oauth_callback(
    provider: str,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    from ..integrations.auth.oauth2_registry import get_oauth2_provider
    try:
        flow_provider = get_oauth2_provider(provider)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown OAuth provider: {provider}")

    agent_id = state  # state carries agent_id

    try:
        result = await flow_provider.handle_callback(
            db=db,
            agent_id=agent_id,
            integration_name=provider,
            code=code,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth callback failed: {str(e)}")

    # OAuth succeeded — now persist the assignment
    from ..repositories.integration_repository import IntegrationRepository
    repo = IntegrationRepository(db)
    repo.assign_to_agent(agent_id, provider)

    return result

@router.get("/agent/{agent_id}", response_model=AgentIntegrationsStatusResponse)
def get_agent_integrations(
    agent_id: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """List integrations split into connected (assigned) and available (unassigned) for an agent."""
    status = svc.get_agent_integrations_status(agent_id)

    connected = [
        AgentAssignedIntegrationDetail(
            id=intg["id"],
            integration_name=intg["name"],
            name=intg["name"],
            display_name=intg.get("display_name", intg["name"]),
            api_type=intg["api_type"],
            base_url=intg["base_url"],
            auth_scheme=intg["auth_scheme"],
            auth_fields=intg["auth_fields"],
            usage_instructions=intg["usage_instructions"],
            display_metadata=intg.get("display_metadata"),
        )
        for intg in status["connected"]
    ]

    available = [
        IntegrationDefBriefResponse(
            name=intg["name"],
            display_name=intg.get("display_name", intg["name"]),
            api_type=intg["api_type"],
            base_url=intg["base_url"],
            auth_scheme=intg["auth_scheme"],
            auth_fields=intg["auth_fields"],
            endpoints=intg["endpoints"],
            usage_instructions=intg["usage_instructions"],
        )
        for intg in status["available"]
    ]

    return AgentIntegrationsStatusResponse(connected=connected, available=available)

@router.get("/{integration_name}/credentials", response_model=Dict[str, Any])
def get_integration_credentials(
    integration_name: str,
    agent_id: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Get decrypted credentials for an agent's integration assignment."""
    credentials = svc.get_agent_credentials(agent_id, integration_name)
    return {
        "integration_name": integration_name,
        "agent_id": agent_id,
        "credentials": credentials,
    }

@router.get("/{integration_name}/unconnected-agents", response_model=List[Dict[str, Any]])
async def get_unconnected_agents(
    integration_name: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Return all agents that are NOT yet connected to the given integration."""
    return await svc.get_unconnected_agents(integration_name)

@router.get("/{integration_name}/logs", response_model=IntegrationLogListResponse)
def get_integration_logs(
    integration_name: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Get recent logs for an integration (used by Dashboard)."""
    logs = svc.get_recent_logs(integration_name)
    return IntegrationLogListResponse(logs=logs)

@router.delete("/unassign")
def unassign_integration_from_agent(
    agent_id: str,
    integration_name: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Remove an integration assignment from an agent."""
    svc.unassign_integration(agent_id, integration_name)
    return {"status": "unassigned", "agent_id": agent_id, "integration_name": integration_name}
