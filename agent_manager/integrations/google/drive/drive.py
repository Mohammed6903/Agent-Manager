from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleDriveIntegration(BaseGoogleIntegration):
    """Integration definition for Google Drive."""

    name = "google_drive"
    display_name = "Google Drive"
    test_connection = ("GET", "drive/v3/about?fields=user")
    base_url = "https://www.googleapis.com/drive/v3"
    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/drive",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/files", description="List files and folders"),
        EndpointDef(method="GET", path="/files/{fileId}", description="Get file metadata"),
        EndpointDef(method="POST", path="/files", description="Create a file or folder"),
        EndpointDef(method="PATCH", path="/files/{fileId}", description="Update file metadata or move a file"),
        EndpointDef(method="DELETE", path="/files/{fileId}", description="Delete a file"),
        EndpointDef(method="GET", path="/files/{fileId}/export", description="Export a Google Doc to another format"),
        EndpointDef(method="POST", path="/files/{fileId}/copy", description="Copy a file"),
        EndpointDef(method="GET", path="/files/{fileId}/permissions", description="List permissions on a file"),
        EndpointDef(method="POST", path="/files/{fileId}/permissions", description="Share a file with a user or group"),
    ]

    usage_instructions = (
        "Google authentication is handled out-of-band via user consent. "
        "Do not supply credentials directly. Use the provided OpenClaw Drive tools to interact with this API natively."
    )
