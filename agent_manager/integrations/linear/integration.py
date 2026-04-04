from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class LinearIntegration(BaseHTTPIntegration):
    """Linear API Integration using OAuth 2.0."""

    name = "linear"
    display_name = "Linear"
    is_active = False
    test_connection = ("POST", "/graphql")
    api_type = "rest"
    base_url = "https://api.linear.app"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import LINEAR_OAUTH_FLOW
    oauth2_provider = LINEAR_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://api.linear.app/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/graphql", description="Execute a GraphQL query or mutation"),
    ]

    usage_instructions = (
        "Linear API integration via OAuth 2.0. Linear uses a GraphQL API — all operations go through POST /graphql with {'query': '...'}. Query issues, projects, teams, cycles, labels, and users."
    )
