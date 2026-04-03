from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class StripeIntegration(BaseHTTPIntegration):
    """Stripe API Integration using Stripe Connect OAuth 2.0 (Standard accounts)."""

    name = "stripe"
    display_name = "Stripe"
    api_type = "rest"
    base_url = "https://api.stripe.com/v1"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from .flow import StripeConnectOAuth2Flow
    oauth2_provider = StripeConnectOAuth2Flow()

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://connect.stripe.com/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        # Balance
        EndpointDef(method="GET", path="/balance", description="Retrieve account balance"),
        # Customers
        EndpointDef(method="GET", path="/customers", description="List customers"),
        EndpointDef(method="GET", path="/customers/{customer_id}", description="Retrieve a customer"),
        EndpointDef(method="POST", path="/customers", description="Create a customer"),
        EndpointDef(method="POST", path="/customers/{customer_id}", description="Update a customer"),
        # Payment Intents
        EndpointDef(method="GET", path="/payment_intents", description="List payment intents"),
        EndpointDef(method="GET", path="/payment_intents/{payment_intent_id}", description="Retrieve a payment intent"),
        EndpointDef(method="POST", path="/payment_intents", description="Create a payment intent"),
        # Invoices
        EndpointDef(method="GET", path="/invoices", description="List invoices"),
        EndpointDef(method="GET", path="/invoices/{invoice_id}", description="Retrieve an invoice"),
        EndpointDef(method="POST", path="/invoices", description="Create an invoice"),
        # Subscriptions
        EndpointDef(method="GET", path="/subscriptions", description="List subscriptions"),
        EndpointDef(method="GET", path="/subscriptions/{subscription_id}", description="Retrieve a subscription"),
        EndpointDef(method="POST", path="/subscriptions", description="Create a subscription"),
        EndpointDef(method="DELETE", path="/subscriptions/{subscription_id}", description="Cancel a subscription"),
        # Products
        EndpointDef(method="GET", path="/products", description="List products"),
        EndpointDef(method="GET", path="/products/{product_id}", description="Retrieve a product"),
        EndpointDef(method="POST", path="/products", description="Create a product"),
        # Prices
        EndpointDef(method="GET", path="/prices", description="List prices"),
        EndpointDef(method="POST", path="/prices", description="Create a price"),
    ]

    usage_instructions = (
        "Stripe API integration via Stripe Connect OAuth 2.0. "
        "Users connect their Stripe account by clicking a button — no secret keys needed. "
        "Bearer token is injected automatically from the connected account. "
        "IMPORTANT: Stripe uses form-encoded POST bodies, not JSON — use data= not json=. "
        "Use GET /customers to list customers, POST /payment_intents to create payments."
    )
