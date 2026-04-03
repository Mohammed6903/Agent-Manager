from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class ChargebeeIntegration(BaseHTTPIntegration):
    """Chargebee API Integration."""

    name = "chargebee"
    display_name = "Chargebee"
    api_type = "rest"
    base_url = "https://{site}.chargebee.com/api/v2"

    auth_scheme: Dict[str, Any] = {
        "type": "basic",
        "username_field": "api_key",
        "password_field": "",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="api_key", label="Chargebee API Key", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/customers", description="List customers"),
        EndpointDef(method="GET", path="/customers/{customer_id}", description="Get a customer"),
        EndpointDef(method="POST", path="/customers", description="Create a customer"),
        EndpointDef(method="POST", path="/customers/{customer_id}", description="Update a customer"),
        EndpointDef(method="GET", path="/subscriptions", description="List subscriptions"),
        EndpointDef(method="GET", path="/subscriptions/{subscription_id}", description="Get a subscription"),
        EndpointDef(method="POST", path="/subscriptions", description="Create a subscription"),
        EndpointDef(method="POST", path="/subscriptions/{subscription_id}/cancel", description="Cancel a subscription"),
        EndpointDef(method="GET", path="/invoices", description="List invoices"),
        EndpointDef(method="GET", path="/invoices/{invoice_id}", description="Get an invoice"),
        EndpointDef(method="GET", path="/plans", description="List plans"),
    ]

    usage_instructions = (
        "Chargebee API integration. Authenticate with API Key. Use GET /customers to list customers. POST /subscriptions to create subscriptions. Chargebee uses form-encoded POST bodies."
    )
