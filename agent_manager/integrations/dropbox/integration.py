from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class DropboxIntegration(BaseHTTPIntegration):
    """Dropbox API Integration using OAuth 2.0."""

    name = "dropbox"
    display_name = "Dropbox"
    is_active = False
    test_connection = ("POST", "/users/get_current_account")
    api_type = "rest"
    base_url = "https://api.dropboxapi.com/2"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import DROPBOX_OAUTH_FLOW
    oauth2_provider = DROPBOX_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://api.dropboxapi.com/oauth2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/files/list_folder", description="List contents of a folder"),
        EndpointDef(method="POST", path="/files/list_folder/continue", description="Continue listing folder contents"),
        EndpointDef(method="POST", path="/files/get_metadata", description="Get metadata for a file or folder"),
        EndpointDef(method="POST", path="/files/search_v2", description="Search for files and folders"),
        EndpointDef(method="POST", path="/files/create_folder_v2", description="Create a folder"),
        EndpointDef(method="POST", path="/files/delete_v2", description="Delete a file or folder"),
        EndpointDef(method="POST", path="/files/move_v2", description="Move a file or folder"),
        EndpointDef(method="POST", path="/files/copy_v2", description="Copy a file or folder"),
        EndpointDef(method="POST", path="/sharing/create_shared_link_with_settings", description="Create a shared link"),
        EndpointDef(method="POST", path="/sharing/list_shared_links", description="List shared links"),
    ]

    usage_instructions = (
        "Dropbox API integration via OAuth 2.0. Users authorize access to their Dropbox files. Dropbox uses POST for all operations with JSON body. Use /files/list_folder to browse, /files/search_v2 to search."
    )
