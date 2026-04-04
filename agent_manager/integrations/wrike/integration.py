from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class WrikeIntegration(BaseHTTPIntegration):
    """Wrike API Integration using OAuth 2.0."""

    name = "wrike"
    display_name = "Wrike"
    is_active = False
    test_connection = ("GET", "/contacts?me=true")
    api_type = "rest"
    base_url = "https://www.wrike.com/api/v4"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import WRIKE_OAUTH_FLOW
    oauth2_provider = WRIKE_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://login.wrike.com/oauth2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/contacts", description="List users/contacts"),
        EndpointDef(method="GET", path="/folders", description="List folders and projects"),
        EndpointDef(method="GET", path="/folders/{folder_id}", description="Get a folder"),
        EndpointDef(method="POST", path="/folders/{folder_id}/folders", description="Create a subfolder"),
        EndpointDef(method="GET", path="/folders/{folder_id}/tasks", description="List tasks in a folder"),
        EndpointDef(method="GET", path="/tasks/{task_id}", description="Get a task"),
        EndpointDef(method="POST", path="/folders/{folder_id}/tasks", description="Create a task"),
        EndpointDef(method="PUT", path="/tasks/{task_id}", description="Update a task"),
        EndpointDef(method="DELETE", path="/tasks/{task_id}", description="Delete a task"),
        EndpointDef(method="GET", path="/spaces", description="List spaces"),
        EndpointDef(method="GET", path="/workflows", description="List workflows"),
    ]

    usage_instructions = (
        "Wrike API integration via OAuth 2.0. Users authorize access to their Wrike workspace. Use GET /folders to list projects. POST /folders/{id}/tasks to create tasks. PUT /tasks/{id} to update."
    )
