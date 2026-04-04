from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class SendGridIntegration(BaseHTTPIntegration):
    """SendGrid API Integration using API Key (bearer auth)."""

    name = "sendgrid"
    display_name = "SendGrid"
    is_active = False
    test_connection = ("GET", "/stats?limit=1")
    api_type = "rest"
    base_url = "https://api.sendgrid.com/v3"

    auth_scheme: Dict[str, Any] = {
        "type": "bearer",
        "token_field": "api_key",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="api_key", label="SendGrid API Key", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/mail/send", description="Send an email"),
        EndpointDef(method="GET", path="/contactdb/lists", description="List contact lists"),
        EndpointDef(method="GET", path="/contactdb/lists/{list_id}", description="Get a contact list"),
        EndpointDef(method="POST", path="/contactdb/lists", description="Create a contact list"),
        EndpointDef(method="GET", path="/contactdb/recipients", description="List recipients"),
        EndpointDef(method="POST", path="/contactdb/recipients", description="Add recipients"),
        EndpointDef(method="GET", path="/templates", description="List email templates"),
        EndpointDef(method="GET", path="/templates/{template_id}", description="Get a template"),
        EndpointDef(method="GET", path="/stats", description="Get email statistics"),
        EndpointDef(method="GET", path="/suppression/bounces", description="List bounced emails"),
    ]

    usage_instructions = (
        "SendGrid API integration. Authenticate with an API Key. Use POST /mail/send to send emails (requires personalizations, from, subject, content). GET /templates to list email templates."
    )
