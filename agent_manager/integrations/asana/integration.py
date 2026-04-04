from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class AsanaIntegration(BaseHTTPIntegration):
    """Asana API Integration using OAuth 2.0."""

    name = "asana"
    display_name = "Asana"
    is_active = False
    test_connection = ("GET", "/users/me")
    api_type = "rest"
    base_url = "https://app.asana.com/api/1.0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import ASANA_OAUTH_FLOW
    oauth2_provider = ASANA_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://app.asana.com/-/oauth_token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/users/me", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/users", description="List users in a workspace"),
        EndpointDef(method="GET", path="/workspaces", description="List workspaces"),
        EndpointDef(method="GET", path="/projects", description="List projects"),
        EndpointDef(method="GET", path="/projects/{project_gid}", description="Get a project"),
        EndpointDef(method="POST", path="/projects", description="Create a project"),
        EndpointDef(method="GET", path="/projects/{project_gid}/tasks", description="List tasks in a project"),
        EndpointDef(method="GET", path="/tasks/{task_gid}", description="Get a task"),
        EndpointDef(method="POST", path="/tasks", description="Create a task"),
        EndpointDef(method="PUT", path="/tasks/{task_gid}", description="Update a task"),
        EndpointDef(method="DELETE", path="/tasks/{task_gid}", description="Delete a task"),
        EndpointDef(method="GET", path="/projects/{project_gid}/sections", description="List sections in a project"),
        EndpointDef(method="POST", path="/projects/{project_gid}/sections", description="Create a section"),
    ]

    usage_instructions = (
        "Asana API integration via OAuth 2.0. Users approve your app to read/write tasks. "
        "Bearer token with auto-refresh is injected automatically. "
        "All request bodies use {'data': {...}} wrapper. "
        "All responses return {'data': ...} wrapper."
    )
