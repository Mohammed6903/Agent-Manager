from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class WordPressIntegration(BaseHTTPIntegration):
    """WordPress API Integration using OAuth 2.0."""

    name = "wordpress"
    display_name = "WordPress"
    is_active = False
    test_connection = ("GET", "/me")
    api_type = "rest"
    base_url = "https://public-api.wordpress.com/rest/v1.1"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import WORDPRESS_OAUTH_FLOW
    oauth2_provider = WORDPRESS_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://public-api.wordpress.com/oauth2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/me", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/me/sites", description="List user's sites"),
        EndpointDef(method="GET", path="/sites/{site_id}/posts", description="List posts"),
        EndpointDef(method="GET", path="/sites/{site_id}/posts/{post_id}", description="Get a post"),
        EndpointDef(method="POST", path="/sites/{site_id}/posts/new", description="Create a post"),
        EndpointDef(method="POST", path="/sites/{site_id}/posts/{post_id}", description="Update a post"),
        EndpointDef(method="POST", path="/sites/{site_id}/posts/{post_id}/delete", description="Delete a post"),
        EndpointDef(method="GET", path="/sites/{site_id}/pages", description="List pages"),
        EndpointDef(method="GET", path="/sites/{site_id}/comments", description="List comments"),
        EndpointDef(method="GET", path="/sites/{site_id}/media", description="List media"),
    ]

    usage_instructions = (
        "WordPress.com API integration via OAuth 2.0. Users authorize access to their WordPress sites. Use GET /me/sites to list sites. POST /sites/{id}/posts/new to create posts. Supports posts, pages, comments, media."
    )
