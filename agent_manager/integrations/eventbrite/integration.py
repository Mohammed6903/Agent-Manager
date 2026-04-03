from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class EventbriteIntegration(BaseHTTPIntegration):
    """Eventbrite API Integration using OAuth 2.0."""

    name = "eventbrite"
    display_name = "Eventbrite"
    api_type = "rest"
    base_url = "https://www.eventbriteapi.com/v3"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import EVENTBRITE_OAUTH_FLOW
    oauth2_provider = EVENTBRITE_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://www.eventbrite.com/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/users/me", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/users/me/organizations", description="List organizations"),
        EndpointDef(method="GET", path="/organizations/{org_id}/events", description="List events for an organization"),
        EndpointDef(method="GET", path="/events/{event_id}", description="Get an event"),
        EndpointDef(method="POST", path="/organizations/{org_id}/events", description="Create an event"),
        EndpointDef(method="POST", path="/events/{event_id}", description="Update an event"),
        EndpointDef(method="GET", path="/events/{event_id}/attendees", description="List attendees for an event"),
        EndpointDef(method="GET", path="/events/{event_id}/orders", description="List orders for an event"),
        EndpointDef(method="GET", path="/events/{event_id}/ticket_classes", description="List ticket types"),
    ]

    usage_instructions = (
        "Eventbrite API integration via OAuth 2.0. Users authorize access to their events. Use GET /users/me/organizations to list orgs. GET /organizations/{id}/events to list events. POST to create events."
    )
