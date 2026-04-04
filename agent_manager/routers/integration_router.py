from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, Response, HTTPException, Request
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
    org_id: Optional[str] = None,  # <- added query param
    svc: IntegrationService = Depends(get_integration_service),
):
    """List all available hardcoded integrations, optionally filtered by organization."""
    return await svc.list_available_integrations(org_id=org_id)

@router.get("/oauth/callback/{provider}")
async def generic_oauth_callback(
    request: Request,
    provider: str,
    state: str,
    code: str = None, # Optional: OAuth 2.0 uses 'code', OAuth 1.0 uses 'oauth_verifier' in query_params
    error: str = None,
    error_description: str = None,
    db: Session = Depends(get_db),
):
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth authorization failed: {error} — {error_description}"
        )

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")
    
    from ..integrations.auth.oauth2_registry import get_oauth2_provider
    try:
        flow_provider = get_oauth2_provider(provider)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown OAuth provider: {provider}")

    # State handles composite values (e.g. "agent_id|integration_name")
    if "|" in state:
        agent_id, integration_name = state.split("|", 1)
    else:
        agent_id = state
        integration_name = provider

    try:
        result = await flow_provider.handle_callback(
            db=db,
            agent_id=agent_id,
            integration_name=integration_name,
            code=code,
            request=request,  # Pass raw request for parsing OAuth 1.0a query params
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth callback failed: {str(e)}")

    # OAuth succeeded — now persist the assignment
    from ..repositories.integration_repository import IntegrationRepository
    repo = IntegrationRepository(db)
    # Extract metadata if returned by the flow provider
    user_metadata = result.get("metadata") if isinstance(result, dict) else None
    repo.assign_to_agent(agent_id, integration_name, metadata=user_metadata)

    # Return a friendly HTML response that closes the popup window
    from fastapi.responses import HTMLResponse
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Authorization Successful</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background-color: #0d1117; color: #c9d1d9; margin: 0; }}
            h1 {{ color: #58a6ff; }}
            p {{ font-size: 16px; margin-bottom: 20px; }}
            .loader {{ border: 4px solid #30363d; border-top: 4px solid #58a6ff; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin-top: 20px; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        </style>
    </head>
    <body>
        <h1>Authorization Successful!</h1>
        <p>Successfully connected {integration_name.capitalize()} to your agent.</p>
        <p>You can close this window now.</p>
        <div class="loader"></div>
        <script>
            // Send a message to the opener window if it exists
            if (window.opener) {{
                window.opener.postMessage({{
                    type: 'OAUTH_SUCCESS',
                    integration: '{integration_name}',
                    agent_id: '{agent_id}'
                }}, '*');
            }}
            // Try to close the window automatically after a short delay
            setTimeout(function() {{
                window.close();
            }}, 2000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

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
    org_id: Optional[str] = None,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Return all agents that are NOT yet connected to the given integration, optionally filtered by organization."""
    return await svc.get_unconnected_agents(integration_name, org_id=org_id)

@router.get("/{integration_name}/logs", response_model=IntegrationLogListResponse)
def get_integration_logs(
    integration_name: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Get recent logs for an integration (used by Dashboard)."""
    logs = svc.get_recent_logs(integration_name)
    return IntegrationLogListResponse(logs=logs)

@router.post("/{integration_name}/test")
async def test_connection(
    integration_name: str,
    agent_id: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Lightweight ping to verify an agent's integration credentials are still valid."""
    return await svc.test_connection(agent_id, integration_name)


@router.delete("/unassign")
def unassign_integration_from_agent(
    agent_id: str,
    integration_name: str,
    svc: IntegrationService = Depends(get_integration_service),
):
    """Remove an integration assignment from an agent."""
    svc.unassign_integration(agent_id, integration_name)
    return {"status": "unassigned", "agent_id": agent_id, "integration_name": integration_name}
