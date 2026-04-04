from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class CalendlyIntegration(BaseHTTPIntegration):
    """Calendly API Integration using OAuth 2.0."""

    name = "calendly"
    display_name = "Calendly"
    is_active = False
    test_connection = ("GET", "/users/me")
    api_type = "rest"
    base_url = "https://api.calendly.com"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import CALENDLY_OAUTH_FLOW
    oauth2_provider = CALENDLY_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://auth.calendly.com/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/users/me", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/event_types", description="List event types"),
        EndpointDef(method="GET", path="/event_types/{event_type_uuid}", description="Get an event type"),
        EndpointDef(method="GET", path="/scheduled_events", description="List scheduled events"),
        EndpointDef(method="GET", path="/scheduled_events/{event_uuid}", description="Get a scheduled event"),
        EndpointDef(method="GET", path="/scheduled_events/{event_uuid}/invitees", description="List invitees for an event"),
        EndpointDef(method="POST", path="/scheduling_links", description="Create a scheduling link"),
    ]

    usage_instructions = (
        "Calendly API integration via OAuth 2.0. Users authorize access to their scheduling data. Use GET /event_types to list bookable event types. GET /scheduled_events to list upcoming bookings."
    )
