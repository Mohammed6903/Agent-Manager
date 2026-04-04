from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class ZohoCRMIntegration(BaseHTTPIntegration):
    """Zoho CRM API Integration using OAuth 2.0."""

    name = "zohocrm"
    display_name = "Zoho CRM"
    is_active = False
    test_connection = ("GET", "/users?type=ActiveUsers")
    api_type = "rest"
    base_url = "https://www.zohoapis.com/crm/v5"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import ZOHO_CRM_OAUTH_FLOW
    oauth2_provider = ZOHO_CRM_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://accounts.zoho.com/oauth/v2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/{module}", description="List records in a module (Leads, Contacts, Deals, etc.)"),
        EndpointDef(method="GET", path="/{module}/{record_id}", description="Get a record"),
        EndpointDef(method="POST", path="/{module}", description="Create records"),
        EndpointDef(method="PUT", path="/{module}/{record_id}", description="Update a record"),
        EndpointDef(method="DELETE", path="/{module}/{record_id}", description="Delete a record"),
        EndpointDef(method="GET", path="/{module}/search", description="Search records in a module"),
        EndpointDef(method="GET", path="/settings/modules", description="List available modules"),
        EndpointDef(method="GET", path="/settings/fields", description="List fields for a module"),
        EndpointDef(method="GET", path="/users", description="List users in the org"),
    ]

    usage_instructions = (
        "Zoho CRM API integration via OAuth 2.0. Users authorize access to their CRM data. Use GET /{module} for Leads, Contacts, Deals, etc. POST /{module} with {'data': [...]} to create records."
    )
