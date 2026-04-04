from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class ConfluenceIntegration(BaseHTTPIntegration):
    """Confluence API Integration using OAuth 2.0."""

    name = "confluence"
    display_name = "Confluence"
    is_active = False
    test_connection = ("GET", "/spaces?limit=1")
    api_type = "rest"
    base_url = "https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/api/v2"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import CONFLUENCE_OAUTH_FLOW
    oauth2_provider = CONFLUENCE_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://auth.atlassian.com/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/pages", description="List pages"),
        EndpointDef(method="GET", path="/pages/{page_id}", description="Get a page"),
        EndpointDef(method="POST", path="/pages", description="Create a page"),
        EndpointDef(method="PUT", path="/pages/{page_id}", description="Update a page"),
        EndpointDef(method="DELETE", path="/pages/{page_id}", description="Delete a page"),
        EndpointDef(method="GET", path="/spaces", description="List spaces"),
        EndpointDef(method="GET", path="/spaces/{space_id}", description="Get a space"),
        EndpointDef(method="GET", path="/pages/{page_id}/children", description="Get child pages"),
        EndpointDef(method="POST", path="/pages/{page_id}/children", description="Create a child page"),
        EndpointDef(method="GET", path="/search", description="Search content with CQL"),
    ]

    usage_instructions = (
        "Confluence API integration via Atlassian OAuth 2.0 (3LO). Users authorize access to their wiki. Use GET /spaces to list spaces. POST /pages to create pages. GET /search?cql=... to search."
    )
