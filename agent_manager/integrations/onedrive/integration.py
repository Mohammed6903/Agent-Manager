from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class OneDriveIntegration(BaseHTTPIntegration):
    """OneDrive API Integration using Microsoft OAuth 2.0 (Graph API)."""

    name = "onedrive"
    display_name = "OneDrive"
    is_active = False
    test_connection = ("GET", "/me/drive")
    api_type = "rest"
    base_url = "https://graph.microsoft.com/v1.0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import ONEDRIVE_OAUTH_FLOW
    oauth2_provider = ONEDRIVE_OAUTH_FLOW

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
        EndpointDef(method="GET", path="/me/drive", description="Get the user's drive info"),
        EndpointDef(method="GET", path="/me/drive/root/children", description="List files in root folder"),
        EndpointDef(method="GET", path="/me/drive/items/{item_id}/children", description="List files in a folder"),
        EndpointDef(method="GET", path="/me/drive/items/{item_id}", description="Get file/folder metadata"),
        EndpointDef(method="GET", path="/me/drive/items/{item_id}/content", description="Download file content"),
        EndpointDef(method="PUT", path="/me/drive/items/{parent_id}:/{filename}:/content", description="Upload a file"),
        EndpointDef(method="PATCH", path="/me/drive/items/{item_id}", description="Update file/folder metadata"),
        EndpointDef(method="DELETE", path="/me/drive/items/{item_id}", description="Delete a file or folder"),
        EndpointDef(method="POST", path="/me/drive/items/{item_id}/copy", description="Copy a file"),
        EndpointDef(method="POST", path="/me/drive/root/children", description="Create a folder"),
        EndpointDef(method="GET", path="/me/drive/search(q='{query}')", description="Search files"),
        EndpointDef(method="POST", path="/me/drive/items/{item_id}/createLink", description="Create a sharing link"),
    ]

    usage_instructions = (
        "OneDrive API integration via Microsoft OAuth 2.0 (Graph API). Users sign in with their Microsoft account. Use GET /me/drive/root/children to list root files. PUT to upload. GET /me/drive/search(q='...') to search files."
    )
