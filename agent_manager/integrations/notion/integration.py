from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class NotionIntegration(BaseHTTPIntegration):
    """Notion API Integration using OAuth 2.0 (Public Integration)."""

    name = "notion"
    display_name = "Notion"
    is_active = False
    test_connection = ("GET", "/users/me")
    api_type = "rest"
    base_url = "https://api.notion.com/v1"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from .flow import NotionOAuth2Flow
    oauth2_provider = NotionOAuth2Flow()

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "extra_headers": {
            "Notion-Version": "2022-06-28",
        },
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    endpoints: List[EndpointDef] = [
        # Search
        EndpointDef(method="POST", path="/search", description="Search pages and databases in workspace"),
        # Pages
        EndpointDef(method="POST", path="/pages", description="Create a new page"),
        EndpointDef(method="GET", path="/pages/{page_id}", description="Retrieve a page"),
        EndpointDef(method="PATCH", path="/pages/{page_id}", description="Update page properties"),
        # Blocks (page content)
        EndpointDef(method="GET", path="/blocks/{block_id}/children", description="Retrieve block children (page content)"),
        EndpointDef(method="PATCH", path="/blocks/{block_id}/children", description="Append block children"),
        EndpointDef(method="PATCH", path="/blocks/{block_id}", description="Update a block"),
        EndpointDef(method="DELETE", path="/blocks/{block_id}", description="Delete a block"),
        # Databases
        EndpointDef(method="POST", path="/databases", description="Create a database"),
        EndpointDef(method="GET", path="/databases/{database_id}", description="Retrieve a database"),
        EndpointDef(method="POST", path="/databases/{database_id}/query", description="Query a database"),
        EndpointDef(method="PATCH", path="/databases/{database_id}", description="Update a database"),
        # Users
        EndpointDef(method="GET", path="/users", description="List all users in workspace"),
        EndpointDef(method="GET", path="/users/{user_id}", description="Retrieve a user"),
        EndpointDef(method="GET", path="/users/me", description="Get the bot user"),
        # Comments
        EndpointDef(method="POST", path="/comments", description="Create a comment on a page or discussion"),
        EndpointDef(method="GET", path="/comments", description="Retrieve comments for a block or page"),
    ]

    usage_instructions = (
        "Notion API integration via OAuth 2.0. Users authorize your app to access their workspace. "
        "Bearer token and Notion-Version header are injected automatically. "
        "Use POST /search to find pages and databases. "
        "Use GET /blocks/{block_id}/children to read page content. "
        "Use POST /databases/{database_id}/query to query database rows. "
        "All request/response bodies use Notion's rich text block format."
    )
