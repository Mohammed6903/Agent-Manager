from typing import List

from .base_google import BaseGoogleIntegration
from ..base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleCalendarIntegration(BaseGoogleIntegration):
    """Integration definition for Google Calendar."""
    
    name = "google_calendar"
    display_name = "Google Calendar"
    base_url = "https://www.googleapis.com/calendar/v3"
    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name",  type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events"
    ]
    
    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/users/me/calendarList", description="List calendars"),
        EndpointDef(method="GET", path="/calendars/{calendarId}/events", description="List events on a calendar"),
        EndpointDef(method="POST", path="/calendars/{calendarId}/events", description="Create an event"),
        EndpointDef(method="PATCH", path="/calendars/{calendarId}/events/{eventId}", description="Update an event"),
        EndpointDef(method="DELETE", path="/calendars/{calendarId}/events/{eventId}", description="Delete an event"),
    ]
    
    usage_instructions = (
        "Google authentication is handled out-of-band via user consent. "
        "Do not supply credentials directly. Use the provided OpenClaw Calendar tools to interact with this API natively."
    )
