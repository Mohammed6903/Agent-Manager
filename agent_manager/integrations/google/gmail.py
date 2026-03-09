from typing import List

from .base_google import BaseGoogleIntegration
from ..base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GmailIntegration(BaseGoogleIntegration):
    """Integration definition for Gmail."""
    
    name = "gmail"
    display_name = "Gmail"
    base_url = "https://gmail.googleapis.com"
    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name",  type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/gmail.modify", 
        "https://www.googleapis.com/auth/gmail.send"
    ]
    
    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/users/me/messages", description="List or search messages"),
        EndpointDef(method="GET", path="/users/me/messages/{id}", description="Get a specific message"),
        EndpointDef(method="POST", path="/users/me/messages/send", description="Send an email"),
        EndpointDef(method="POST", path="/users/me/messages/{id}/reply", description="Reply to an email thread"),
        EndpointDef(method="POST", path="/users/me/messages/batchModify", description="Modify message labels (e.g., mark read)"),
        EndpointDef(method="GET", path="/users/me/drafts", description="List drafts"),
        EndpointDef(method="POST", path="/users/me/drafts", description="Create a draft"),
        EndpointDef(method="POST", path="/users/me/drafts/send", description="Send a draft"),
    ]
    
    usage_instructions = (
        "Google authentication is handled out-of-band via user consent. "
        "Do not supply credentials directly. Use the provided OpenClaw Gmail tools to interact with this API natively."
    )
