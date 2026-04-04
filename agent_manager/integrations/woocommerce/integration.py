from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class WooCommerceIntegration(BaseHTTPIntegration):
    """WooCommerce API Integration."""

    name = "woocommerce"
    display_name = "WooCommerce"
    is_active = False
    test_connection = ("GET", "/products?per_page=1")
    api_type = "rest"
    base_url = "https://{store_url}/wp-json/wc/v3"

    auth_scheme: Dict[str, Any] = {
        "type": "basic",
        "username_field": "consumer_key",
        "password_field": "consumer_secret",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="consumer_key", label="Consumer Key", required=True),
        AuthFieldDef(name="consumer_secret", label="Consumer Secret", required=True),
        AuthFieldDef(name="store_url", label="Store URL (e.g. mystore.com)", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/products", description="List products"),
        EndpointDef(method="GET", path="/products/{product_id}", description="Get a product"),
        EndpointDef(method="POST", path="/products", description="Create a product"),
        EndpointDef(method="PUT", path="/products/{product_id}", description="Update a product"),
        EndpointDef(method="DELETE", path="/products/{product_id}", description="Delete a product"),
        EndpointDef(method="GET", path="/orders", description="List orders"),
        EndpointDef(method="GET", path="/orders/{order_id}", description="Get an order"),
        EndpointDef(method="PUT", path="/orders/{order_id}", description="Update an order"),
        EndpointDef(method="GET", path="/customers", description="List customers"),
        EndpointDef(method="GET", path="/customers/{customer_id}", description="Get a customer"),
        EndpointDef(method="POST", path="/customers", description="Create a customer"),
        EndpointDef(method="GET", path="/coupons", description="List coupons"),
    ]

    usage_instructions = (
        "WooCommerce REST API integration. Authenticate with Consumer Key and Consumer Secret (Basic auth). Use GET /products to list products. POST /products to create. GET /orders to list orders."
    )
