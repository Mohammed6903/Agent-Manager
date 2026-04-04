from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class HubSpotIntegration(BaseHTTPIntegration):
    """HubSpot CRM API Integration using OAuth 2.0 (Public App)."""

    name = "hubspot"
    display_name = "HubSpot"
    is_active = False
    test_connection = ("GET", "/crm/v3/objects/contacts?limit=1")
    api_type = "rest"
    base_url = "https://api.hubapi.com"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import HUBSPOT_OAUTH_FLOW
    oauth2_provider = HUBSPOT_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/crm/v3/objects/contacts", description="List contacts"),
        EndpointDef(method="GET", path="/crm/v3/objects/contacts/{contact_id}", description="Get a contact"),
        EndpointDef(method="POST", path="/crm/v3/objects/contacts", description="Create a contact"),
        EndpointDef(method="PATCH", path="/crm/v3/objects/contacts/{contact_id}", description="Update a contact"),
        EndpointDef(method="POST", path="/crm/v3/objects/contacts/search", description="Search contacts"),
        EndpointDef(method="GET", path="/crm/v3/objects/companies", description="List companies"),
        EndpointDef(method="GET", path="/crm/v3/objects/companies/{company_id}", description="Get a company"),
        EndpointDef(method="POST", path="/crm/v3/objects/companies", description="Create a company"),
        EndpointDef(method="PATCH", path="/crm/v3/objects/companies/{company_id}", description="Update a company"),
        EndpointDef(method="POST", path="/crm/v3/objects/companies/search", description="Search companies"),
        EndpointDef(method="GET", path="/crm/v3/objects/deals", description="List deals"),
        EndpointDef(method="GET", path="/crm/v3/objects/deals/{deal_id}", description="Get a deal"),
        EndpointDef(method="POST", path="/crm/v3/objects/deals", description="Create a deal"),
        EndpointDef(method="PATCH", path="/crm/v3/objects/deals/{deal_id}", description="Update a deal"),
        EndpointDef(method="POST", path="/crm/v3/objects/deals/search", description="Search deals"),
        EndpointDef(method="GET", path="/crm/v3/objects/tickets", description="List tickets"),
        EndpointDef(method="GET", path="/crm/v3/objects/tickets/{ticket_id}", description="Get a ticket"),
        EndpointDef(method="POST", path="/crm/v3/objects/tickets", description="Create a ticket"),
        EndpointDef(method="PATCH", path="/crm/v3/objects/tickets/{ticket_id}", description="Update a ticket"),
        EndpointDef(method="GET", path="/crm/v3/owners", description="List owners"),
        EndpointDef(method="GET", path="/crm/v3/owners/{owner_id}", description="Get an owner"),
    ]

    usage_instructions = (
        "HubSpot CRM API integration via OAuth 2.0 (Public App). "
        "Users install your app from HubSpot to grant CRM access. "
        "Bearer token with auto-refresh is injected automatically. "
        "Create/update objects with {'properties': {...}} body. "
        "Search with {'filterGroups': [...], 'sorts': [...]}."
    )
