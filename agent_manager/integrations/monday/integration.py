from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class MondayIntegration(BaseHTTPIntegration):
    """Monday API Integration using OAuth 2.0."""

    name = "monday"
    display_name = "Monday"
    api_type = "rest"
    base_url = "https://api.monday.com/v2"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import MONDAY_OAUTH_FLOW
    oauth2_provider = MONDAY_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://auth.monday.com/oauth2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/", description="Execute a GraphQL query or mutation"),
    ]

    usage_instructions = (
        "Monday.com API integration via OAuth 2.0. Monday uses a GraphQL API — all operations go through POST / with {'query': '...'}. Use boards, items, columns, groups queries."
    )
