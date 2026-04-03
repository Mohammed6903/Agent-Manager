from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class ClickUpIntegration(BaseHTTPIntegration):
    """ClickUp API Integration using OAuth 2.0."""

    name = "clickup"
    display_name = "ClickUp"
    api_type = "rest"
    base_url = "https://api.clickup.com/api/v2"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import CLICKUP_OAUTH_FLOW
    oauth2_provider = CLICKUP_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://api.clickup.com/api/v2/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/team", description="List authorized teams/workspaces"),
        EndpointDef(method="GET", path="/team/{team_id}/space", description="List spaces in a team"),
        EndpointDef(method="GET", path="/space/{space_id}", description="Get a space"),
        EndpointDef(method="POST", path="/team/{team_id}/space", description="Create a space"),
        EndpointDef(method="GET", path="/space/{space_id}/folder", description="List folders in a space"),
        EndpointDef(method="GET", path="/folder/{folder_id}", description="Get a folder"),
        EndpointDef(method="POST", path="/space/{space_id}/folder", description="Create a folder"),
        EndpointDef(method="GET", path="/folder/{folder_id}/list", description="List lists in a folder"),
        EndpointDef(method="GET", path="/list/{list_id}", description="Get a list"),
        EndpointDef(method="POST", path="/folder/{folder_id}/list", description="Create a list"),
        EndpointDef(method="GET", path="/list/{list_id}/task", description="List tasks in a list"),
        EndpointDef(method="GET", path="/task/{task_id}", description="Get a task"),
        EndpointDef(method="POST", path="/list/{list_id}/task", description="Create a task"),
        EndpointDef(method="PUT", path="/task/{task_id}", description="Update a task"),
        EndpointDef(method="DELETE", path="/task/{task_id}", description="Delete a task"),
        EndpointDef(method="GET", path="/task/{task_id}/comment", description="List comments on a task"),
        EndpointDef(method="POST", path="/task/{task_id}/comment", description="Create a comment on a task"),
    ]

    usage_instructions = (
        "ClickUp API integration via OAuth 2.0. Users select which workspaces your app can access. "
        "Bearer token is injected automatically. "
        "Navigate: team -> space -> folder -> list -> task."
    )
