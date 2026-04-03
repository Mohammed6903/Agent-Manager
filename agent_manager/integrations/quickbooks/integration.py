from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class QuickBooksIntegration(BaseHTTPIntegration):
    """QuickBooks API Integration using OAuth 2.0."""

    name = "quickbooks"
    display_name = "QuickBooks"
    api_type = "rest"
    base_url = "https://quickbooks.api.intuit.com/v3"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import QUICKBOOKS_OAUTH_FLOW
    oauth2_provider = QUICKBOOKS_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/company/{realm_id}/query", description="Execute a QuickBooks query (pass query param)"),
        EndpointDef(method="GET", path="/company/{realm_id}/customer/{customer_id}", description="Get a customer"),
        EndpointDef(method="POST", path="/company/{realm_id}/customer", description="Create a customer"),
        EndpointDef(method="POST", path="/company/{realm_id}/invoice", description="Create an invoice"),
        EndpointDef(method="GET", path="/company/{realm_id}/invoice/{invoice_id}", description="Get an invoice"),
        EndpointDef(method="POST", path="/company/{realm_id}/payment", description="Create a payment"),
        EndpointDef(method="GET", path="/company/{realm_id}/companyinfo/{realm_id}", description="Get company info"),
        EndpointDef(method="GET", path="/company/{realm_id}/account/{account_id}", description="Get an account"),
        EndpointDef(method="POST", path="/company/{realm_id}/bill", description="Create a bill"),
        EndpointDef(method="POST", path="/company/{realm_id}/vendor", description="Create a vendor"),
    ]

    usage_instructions = (
        "QuickBooks API integration via Intuit OAuth 2.0. Users authorize access to their QuickBooks company. Use GET /company/{realm_id}/query?query=SELECT * FROM Customer for SOQL-like queries. POST to create invoices, customers, payments."
    )
