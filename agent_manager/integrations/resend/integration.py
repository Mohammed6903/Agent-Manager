from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class ResendIntegration(BaseHTTPIntegration):
    """Resend API Integration using API Key (bearer auth)."""

    name = "resend"
    display_name = "Resend"
    api_type = "rest"
    base_url = "https://api.resend.com"

    auth_scheme: Dict[str, Any] = {
        "type": "bearer",
        "token_field": "api_key",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="api_key", label="Resend API Key", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/emails", description="Send an email"),
        EndpointDef(method="GET", path="/emails/{email_id}", description="Get email details"),
        EndpointDef(method="GET", path="/domains", description="List domains"),
        EndpointDef(method="GET", path="/domains/{domain_id}", description="Get a domain"),
        EndpointDef(method="POST", path="/domains", description="Add a domain"),
        EndpointDef(method="GET", path="/api-keys", description="List API keys"),
        EndpointDef(method="POST", path="/api-keys", description="Create an API key"),
        EndpointDef(method="GET", path="/audiences", description="List audiences"),
        EndpointDef(method="POST", path="/audiences", description="Create an audience"),
        EndpointDef(method="GET", path="/audiences/{audience_id}/contacts", description="List contacts in an audience"),
        EndpointDef(method="POST", path="/audiences/{audience_id}/contacts", description="Add a contact to an audience"),
    ]

    usage_instructions = (
        "Resend API integration. Authenticate with an API Key. Use POST /emails to send emails (requires 'from', 'to', 'subject'). GET /domains to list verified domains. POST /audiences/{id}/contacts to manage contacts."
    )
