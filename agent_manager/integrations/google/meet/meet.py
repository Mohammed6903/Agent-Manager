from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType

class GoogleMeetIntegration(BaseGoogleIntegration):
    """Integration definition for Google Meet."""

    name = "google_meet"
    display_name = "Google Meet"
    test_connection = ("GET", "meet/v2/spaces")
    base_url = "https://meet.googleapis.com/v2"

    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]
    
    scopes: List[str] = [
        "https://www.googleapis.com/auth/meetings.space.created",
        "https://www.googleapis.com/auth/meetings.space.readonly"
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/spaces", description="Create a new Meet space and get a meeting URL"),
        EndpointDef(method="GET", path="/spaces/{space_id}", description="Get details about a meeting space"),
    ]

    usage_instructions = (
        "Use this to generate instant meeting links. To schedule a Meet for the future, "
        "it is often better to use the Calendar API with conferenceData enabled."
    )