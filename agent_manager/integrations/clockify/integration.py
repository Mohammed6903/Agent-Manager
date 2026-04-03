from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class ClockifyIntegration(BaseHTTPIntegration):
    """Clockify API Integration."""

    name = "clockify"
    display_name = "Clockify"
    api_type = "rest"
    base_url = "https://api.clockify.me/api/v1"

    auth_scheme: Dict[str, Any] = {
        "type": "api_key_header",
        "header_name": "X-Api-Key",
        "token_field": "api_key",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="api_key", label="Clockify API Key", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/user", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/workspaces", description="List workspaces"),
        EndpointDef(method="GET", path="/workspaces/{workspace_id}/projects", description="List projects in a workspace"),
        EndpointDef(method="POST", path="/workspaces/{workspace_id}/projects", description="Create a project"),
        EndpointDef(method="GET", path="/workspaces/{workspace_id}/users", description="List users in a workspace"),
        EndpointDef(method="GET", path="/workspaces/{workspace_id}/time-entries", description="List time entries"),
        EndpointDef(method="POST", path="/workspaces/{workspace_id}/time-entries", description="Create a time entry"),
        EndpointDef(method="GET", path="/workspaces/{workspace_id}/clients", description="List clients"),
        EndpointDef(method="GET", path="/workspaces/{workspace_id}/tags", description="List tags"),
    ]

    usage_instructions = (
        "Clockify API integration. Authenticate with API Key (X-Api-Key header). Use GET /workspaces to list workspaces. POST /workspaces/{id}/time-entries to log time. GET /workspaces/{id}/projects for projects."
    )
