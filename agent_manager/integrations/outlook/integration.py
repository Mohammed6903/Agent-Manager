from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class OutlookIntegration(BaseHTTPIntegration):
    """Outlook API Integration using Microsoft OAuth 2.0 (Graph API)."""

    name = "outlook"
    display_name = "Outlook"
    is_active = False
    test_connection = ("GET", "/me")
    api_type = "rest"
    base_url = "https://graph.microsoft.com/v1.0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import OUTLOOK_OAUTH_FLOW
    oauth2_provider = OUTLOOK_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/me", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/me/messages", description="List messages in inbox"),
        EndpointDef(method="GET", path="/me/messages/{message_id}", description="Get a message"),
        EndpointDef(method="POST", path="/me/sendMail", description="Send an email"),
        EndpointDef(method="POST", path="/me/messages/{message_id}/reply", description="Reply to a message"),
        EndpointDef(method="POST", path="/me/messages/{message_id}/forward", description="Forward a message"),
        EndpointDef(method="PATCH", path="/me/messages/{message_id}", description="Update a message (read/unread, categories)"),
        EndpointDef(method="DELETE", path="/me/messages/{message_id}", description="Delete a message"),
        EndpointDef(method="GET", path="/me/messages?$search=\"{query}\"", description="Search messages"),
        EndpointDef(method="GET", path="/me/mailFolders", description="List mail folders"),
        EndpointDef(method="GET", path="/me/calendar/events", description="List calendar events"),
        EndpointDef(method="POST", path="/me/calendar/events", description="Create a calendar event"),
        EndpointDef(method="GET", path="/me/calendar/events/{event_id}", description="Get a calendar event"),
        EndpointDef(method="PATCH", path="/me/calendar/events/{event_id}", description="Update a calendar event"),
        EndpointDef(method="DELETE", path="/me/calendar/events/{event_id}", description="Delete a calendar event"),
        EndpointDef(method="GET", path="/me/contacts", description="List contacts"),
        EndpointDef(method="POST", path="/me/contacts", description="Create a contact"),
    ]

    usage_instructions = (
        "Outlook API integration via Microsoft OAuth 2.0 (Graph API). Users sign in with their Microsoft account. Use GET /me/messages to read emails. POST /me/sendMail to send (body: {message: {subject, body, toRecipients}}). GET /me/calendar/events for calendar. GET /me/contacts for contacts."
    )
