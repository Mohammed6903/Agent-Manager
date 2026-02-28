from typing import List, Dict, Any
import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.integration import (
    GlobalIntegrationCreate,
    GlobalIntegrationUpdate,
    GlobalIntegrationResponse,
    AgentIntegrationAssignRequest,
    AgentIntegrationListResponse,
    AgentAssignedIntegrationDetail,
    IntegrationLogListResponse,
    IntegrationProxyRequest,
)
from ..services.integration_service import IntegrationService

router = APIRouter(tags=["Integration Management"])

def get_integration_service(db: Session = Depends(get_db)) -> IntegrationService:
    return IntegrationService(db)

# -- Global CRUD --

@router.post("", response_model=GlobalIntegrationResponse)
def create_global_integration(
    req: GlobalIntegrationCreate,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Create a new global integration."""
    return svc.create_global_integration(req)

@router.get("", response_model=List[GlobalIntegrationResponse])
def list_global_integrations(
    svc: IntegrationService = Depends(get_integration_service),
):
    """List all available global integrations."""
    return svc.list_global_integrations()

@router.get("/{integration_id}", response_model=GlobalIntegrationResponse)
def get_global_integration(
    integration_id: uuid.UUID,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Get a specific global integration."""
    return svc.get_global_integration(integration_id)

@router.patch("/{integration_id}", response_model=GlobalIntegrationResponse)
def update_global_integration(
    integration_id: uuid.UUID,
    req: GlobalIntegrationUpdate,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Update a specific global integration."""
    return svc.update_global_integration(integration_id, req)
    
@router.delete("/{integration_id}")
def delete_global_integration(
    integration_id: uuid.UUID,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Delete a specific global integration."""
    svc.delete_global_integration(integration_id)
    return Response(status_code=204)


# -- Agent Assignment & Usage --

@router.post("/{integration_id}/assign")
def assign_integration_to_agent(
    integration_id: uuid.UUID,
    req: AgentIntegrationAssignRequest,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Assign a global integration to an agent."""
    svc.assign_integration(integration_id, req)
    return Response(status_code=200)

@router.get("/agent/{agent_id}", response_model=AgentIntegrationListResponse)
def get_agent_integrations(
    agent_id: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """(Skill Endpoint) List integrations assigned to the agent."""
    integrations = svc.get_agent_integrations(agent_id)
    # Filter the response to only include info relevant to the agent (auth_fields + instructions)
    filtered = []
    for intg in integrations:
        filtered.append(AgentAssignedIntegrationDetail(
            integration_id=intg.id,
            name=intg.name,
            type=intg.type,
            base_url=intg.base_url,
            auth_scheme=intg.auth_scheme,
            auth_fields=[f for f in intg.auth_fields],
            usage_instructions=intg.usage_instructions
        ))
    return AgentIntegrationListResponse(integrations=filtered)

@router.get("/{integration_id}/credentials", response_model=Dict[str, Any])
def get_integration_credentials(
    integration_id: uuid.UUID,
    agent_id: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Get decrypted credentials for an agent's integration assignment."""
    credentials = svc.get_agent_credentials(agent_id, integration_id)
    return {
        "integration_id": str(integration_id),
        "agent_id": agent_id,
        "credentials": credentials,
    }

@router.post("/{integration_id}/proxy")
async def proxy_integration_request(
    integration_id: uuid.UUID,
    req: IntegrationProxyRequest,
    svc: IntegrationService = Depends(get_integration_service),
):
    """(Skill Endpoint) Makes a request to the third-party API securely on behalf of the agent."""
    import httpx
    try:
        resp = await svc.async_proxy_request(integration_id, req)
        
        # Pass the HTTP response back as JSON context
        try:
             json_data = resp.json()
        except:
             json_data = resp.text
             
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json")
        )
    except httpx.RequestError as e:
        return Response(status_code=502, content=f"Gateway error: {str(e)}")


@router.get("/{integration_id}/logs", response_model=IntegrationLogListResponse)
def get_integration_logs(
    integration_id: uuid.UUID,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Get recent logs for an integration (used by Dashboard)."""
    logs = svc.get_recent_logs(integration_id)
    return IntegrationLogListResponse(logs=logs)
