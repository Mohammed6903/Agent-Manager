from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleFormsIntegration(BaseGoogleIntegration):
    """Integration definition for Google Forms."""

    name = "google_forms"
    display_name = "Google Forms"
    base_url = "https://forms.googleapis.com/v1"

    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/forms.body",
        "https://www.googleapis.com/auth/forms.body.readonly",
        "https://www.googleapis.com/auth/forms.responses.readonly",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/forms/{form_id}", description="Get a form"),
        EndpointDef(method="POST", path="/forms", description="Create a new form"),
        EndpointDef(method="PATCH", path="/forms/{form_id}", description="Update a form"),
        EndpointDef(method="POST", path="/forms/{form_id}:batchUpdate", description="Batch update form items"),
        EndpointDef(method="GET", path="/forms/{form_id}/responses", description="List form responses"),
        EndpointDef(method="GET", path="/forms/{form_id}/responses/{response_id}", description="Get a specific response"),
    ]

    usage_instructions = (
        "Google Forms API. Use GET /forms/{id} to read form structure. "
        "POST /forms to create. GET /forms/{id}/responses to list submissions. "
        "POST /forms/{id}:batchUpdate to add/remove questions."
    )
