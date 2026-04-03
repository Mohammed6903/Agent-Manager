from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class BoxIntegration(BaseHTTPIntegration):
    """Box API Integration using OAuth 2.0."""

    name = "box"
    display_name = "Box"
    api_type = "rest"
    base_url = "https://api.box.com/2.0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import BOX_OAUTH_FLOW
    oauth2_provider = BOX_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://api.box.com/oauth2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/users/me", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/folders/{folder_id}/items", description="List items in a folder"),
        EndpointDef(method="GET", path="/folders/{folder_id}", description="Get a folder"),
        EndpointDef(method="POST", path="/folders", description="Create a folder"),
        EndpointDef(method="DELETE", path="/folders/{folder_id}", description="Delete a folder"),
        EndpointDef(method="GET", path="/files/{file_id}", description="Get file info"),
        EndpointDef(method="DELETE", path="/files/{file_id}", description="Delete a file"),
        EndpointDef(method="GET", path="/search", description="Search for files and folders"),
        EndpointDef(method="POST", path="/files/{file_id}/copy", description="Copy a file"),
        EndpointDef(method="GET", path="/shared_items", description="Get shared item info"),
    ]

    usage_instructions = (
        "Box API integration via OAuth 2.0. Users authorize access to their Box files. Use GET /folders/0/items to list root folder. GET /search?query=... to search. POST /folders to create folders."
    )
