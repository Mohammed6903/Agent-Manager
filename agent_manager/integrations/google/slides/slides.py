from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleSlidesIntegration(BaseGoogleIntegration):
    """Integration definition for Google Slides."""

    name = "google_slides"
    display_name = "Google Slides"
    base_url = "https://slides.googleapis.com/v1"

    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/presentations.readonly",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/presentations/{presentation_id}", description="Get a presentation"),
        EndpointDef(method="POST", path="/presentations", description="Create a new presentation"),
        EndpointDef(method="POST", path="/presentations/{presentation_id}:batchUpdate", description="Apply batch updates to a presentation"),
        EndpointDef(method="GET", path="/presentations/{presentation_id}/pages/{page_id}", description="Get a specific slide page"),
        EndpointDef(method="GET", path="/presentations/{presentation_id}/pages/{page_id}/thumbnails", description="Get slide thumbnail"),
    ]

    usage_instructions = (
        "Google Slides API. Use GET /presentations/{id} to read slides. "
        "POST /presentations to create new. POST /presentations/{id}:batchUpdate for modifications "
        "(insert slides, add text, shapes, images, delete slides, reorder)."
    )
