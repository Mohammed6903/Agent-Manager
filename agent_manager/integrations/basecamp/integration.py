from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class BasecampIntegration(BaseHTTPIntegration):
    """Basecamp API Integration using OAuth 2.0."""

    name = "basecamp"
    display_name = "Basecamp"
    is_active = False
    test_connection = ("GET", "/authorization.json")
    api_type = "rest"
    base_url = "https://3.basecampapi.com"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import BASECAMP_OAUTH_FLOW
    oauth2_provider = BASECAMP_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://launchpad.37signals.com/authorization/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/authorization.json", description="Get authorization info and accounts"),
        EndpointDef(method="GET", path="/{account_id}/projects.json", description="List projects"),
        EndpointDef(method="GET", path="/{account_id}/projects/{project_id}.json", description="Get a project"),
        EndpointDef(method="POST", path="/{account_id}/projects.json", description="Create a project"),
        EndpointDef(method="GET", path="/{account_id}/buckets/{project_id}/todolists.json", description="List to-do lists"),
        EndpointDef(method="GET", path="/{account_id}/buckets/{project_id}/todolists/{todolist_id}/todos.json", description="List to-dos"),
        EndpointDef(method="POST", path="/{account_id}/buckets/{project_id}/todolists/{todolist_id}/todos.json", description="Create a to-do"),
        EndpointDef(method="GET", path="/{account_id}/people.json", description="List people"),
    ]

    usage_instructions = (
        "Basecamp API integration via OAuth 2.0. Users authorize access to their Basecamp account. Use GET /authorization.json to discover accounts. GET /{account_id}/projects.json to list projects."
    )
