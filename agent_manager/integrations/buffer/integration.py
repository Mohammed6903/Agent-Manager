from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class BufferIntegration(BaseHTTPIntegration):
    """Buffer API Integration using OAuth 2.0."""

    name = "buffer"
    display_name = "Buffer"
    is_active = False
    test_connection = ("GET", "/user.json")
    api_type = "rest"
    base_url = "https://api.bufferapp.com/1"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import BUFFER_OAUTH_FLOW
    oauth2_provider = BUFFER_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://api.bufferapp.com/1/oauth2/token.json",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/user.json", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/profiles.json", description="List social media profiles"),
        EndpointDef(method="GET", path="/profiles/{profile_id}.json", description="Get a profile"),
        EndpointDef(method="GET", path="/profiles/{profile_id}/updates/pending.json", description="Get pending updates for a profile"),
        EndpointDef(method="GET", path="/profiles/{profile_id}/updates/sent.json", description="Get sent updates for a profile"),
        EndpointDef(method="POST", path="/updates/create.json", description="Create a new social media update"),
        EndpointDef(method="POST", path="/updates/{update_id}/update.json", description="Update an existing update"),
        EndpointDef(method="POST", path="/updates/{update_id}/destroy.json", description="Delete an update"),
    ]

    usage_instructions = (
        "Buffer API integration via OAuth 2.0. Users authorize access to their social media profiles. Use GET /profiles.json to list connected social accounts. POST /updates/create.json to schedule posts."
    )
