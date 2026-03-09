from typing import List

from .base_google import BaseGoogleIntegration
from ..base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleDocsIntegration(BaseGoogleIntegration):
    """Integration definition for Google Docs."""

    name = "google_docs"
    display_name = "Google Docs"
    base_url = "https://docs.googleapis.com/v1"
    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/documents",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/documents", description="Create a new document"),
        EndpointDef(method="GET", path="/documents/{documentId}", description="Get full document content and metadata"),
        EndpointDef(method="POST", path="/documents/{documentId}:batchUpdate", description="Apply formatting, insertions, or deletions"),
    ]

    usage_instructions = (
        "Google authentication is handled out-of-band via user consent. "
        "Do not supply credentials directly. Use the provided OpenClaw Docs tools to interact with this API natively."
    )
