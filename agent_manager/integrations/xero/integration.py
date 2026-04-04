from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class XeroIntegration(BaseHTTPIntegration):
    """Xero API Integration using OAuth 2.0."""

    name = "xero"
    display_name = "Xero"
    is_active = False
    test_connection = ("GET", "/Organisation")
    api_type = "rest"
    base_url = "https://api.xero.com/api.xro/2.0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import XERO_OAUTH_FLOW
    oauth2_provider = XERO_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://identity.xero.com/connect/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/Contacts", description="List contacts"),
        EndpointDef(method="GET", path="/Contacts/{contact_id}", description="Get a contact"),
        EndpointDef(method="POST", path="/Contacts", description="Create a contact"),
        EndpointDef(method="GET", path="/Invoices", description="List invoices"),
        EndpointDef(method="GET", path="/Invoices/{invoice_id}", description="Get an invoice"),
        EndpointDef(method="POST", path="/Invoices", description="Create an invoice"),
        EndpointDef(method="GET", path="/Accounts", description="List accounts"),
        EndpointDef(method="GET", path="/BankTransactions", description="List bank transactions"),
        EndpointDef(method="POST", path="/Payments", description="Create a payment"),
        EndpointDef(method="GET", path="/Organisation", description="Get organisation info"),
    ]

    usage_instructions = (
        "Xero API integration via OAuth 2.0. Users authorize access to their Xero organisation. Use GET /Invoices to list invoices. POST /Invoices to create. GET /Contacts for customer list."
    )
