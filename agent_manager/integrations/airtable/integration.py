from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class AirtableIntegration(BaseHTTPIntegration):
    """Airtable API Integration using OAuth 2.0."""

    name = "airtable"
    display_name = "Airtable"
    is_active = False
    test_connection = ("GET", "/meta/bases")
    api_type = "rest"
    base_url = "https://api.airtable.com/v0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import AIRTABLE_OAUTH_FLOW
    oauth2_provider = AIRTABLE_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://airtable.com/oauth2/v1/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/meta/bases", description="List all accessible bases"),
        EndpointDef(method="GET", path="/meta/bases/{base_id}/tables", description="List tables in a base"),
        EndpointDef(method="GET", path="/{base_id}/{table_id_or_name}", description="List records in a table"),
        EndpointDef(method="GET", path="/{base_id}/{table_id_or_name}/{record_id}", description="Get a record"),
        EndpointDef(method="POST", path="/{base_id}/{table_id_or_name}", description="Create records"),
        EndpointDef(method="PATCH", path="/{base_id}/{table_id_or_name}", description="Update records"),
        EndpointDef(method="DELETE", path="/{base_id}/{table_id_or_name}", description="Delete records"),
    ]

    usage_instructions = (
        "Airtable API integration via OAuth 2.0. "
        "Users authorize access to specific bases/workspaces. "
        "Bearer token with auto-refresh is injected automatically. "
        "Use GET /meta/bases to list bases. POST to create records."
    )
