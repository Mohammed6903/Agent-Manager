from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class WhatsAppBusinessIntegration(BaseHTTPIntegration):
    """WhatsApp Business API Integration."""

    name = "whatsapp"
    display_name = "WhatsApp Business"
    api_type = "rest"
    base_url = "https://graph.facebook.com/v19.0"

    auth_scheme: Dict[str, Any] = {
        "type": "bearer",
        "token_field": "access_token",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="access_token", label="WhatsApp Business Access Token", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/{phone_number_id}/messages", description="Send a message"),
        EndpointDef(method="GET", path="/{phone_number_id}", description="Get phone number info"),
        EndpointDef(method="GET", path="/{business_account_id}/phone_numbers", description="List phone numbers"),
        EndpointDef(method="POST", path="/{phone_number_id}/register", description="Register a phone number"),
        EndpointDef(method="GET", path="/{business_account_id}/message_templates", description="List message templates"),
        EndpointDef(method="POST", path="/{business_account_id}/message_templates", description="Create a message template"),
        EndpointDef(method="GET", path="/{media_id}", description="Get media URL"),
        EndpointDef(method="POST", path="/{phone_number_id}/media", description="Upload media"),
    ]

    usage_instructions = (
        "WhatsApp Business API integration via Meta's Graph API. Authenticate with a permanent access token. Use POST /{phone_number_id}/messages to send messages. Supports text, template, image, and document messages."
    )
