from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class SquareIntegration(BaseHTTPIntegration):
    """Square API Integration using OAuth 2.0."""

    name = "square"
    display_name = "Square"
    api_type = "rest"
    base_url = "https://connect.squareup.com/v2"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import SQUARE_OAUTH_FLOW
    oauth2_provider = SQUARE_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://connect.squareup.com/oauth2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/locations", description="List locations"),
        EndpointDef(method="POST", path="/payments", description="Create a payment"),
        EndpointDef(method="GET", path="/payments", description="List payments"),
        EndpointDef(method="GET", path="/payments/{payment_id}", description="Get a payment"),
        EndpointDef(method="POST", path="/customers", description="Create a customer"),
        EndpointDef(method="GET", path="/customers", description="List customers"),
        EndpointDef(method="GET", path="/customers/{customer_id}", description="Get a customer"),
        EndpointDef(method="PUT", path="/customers/{customer_id}", description="Update a customer"),
        EndpointDef(method="POST", path="/orders", description="Create an order"),
        EndpointDef(method="GET", path="/catalog/list", description="List catalog items"),
        EndpointDef(method="POST", path="/invoices", description="Create an invoice"),
        EndpointDef(method="GET", path="/invoices", description="List invoices"),
    ]

    usage_instructions = (
        "Square API integration via OAuth 2.0. Users authorize access to their Square account. Use GET /locations to list business locations. POST /payments to process payments. GET /customers for customer data."
    )
