from typing import Dict, List, Any

from .base import BaseSDKIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class LinkedInIntegration(BaseSDKIntegration):
    """LinkedIn API v2 Integration using OAuth 2.0."""
    
    name = "linkedin"
    display_name = "LinkedIn"
    api_type = "sdk"
    base_url = "https://api.linkedin.com/v2"
    
    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name",  type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
    }
    
    auth_flow = AuthFlowType.OAUTH2_LINKEDIN
    
    from .auth.linkedin_flow import LinkedInOAuth2Flow
    oauth2_provider = LinkedInOAuth2Flow()
    
    auth_fields: List[AuthFieldDef] = []
    
    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/userinfo", description="Get authenticated user profile (OpenID Connect)"),
        EndpointDef(method="GET", path="/me", description="Get authenticated member's profile"),
        EndpointDef(method="POST", path="/ugcPosts", description="Create a post / share content"),
        EndpointDef(method="GET", path="/ugcPosts/{ugcPostUrn}", description="Get a specific post"),
        EndpointDef(method="DELETE", path="/ugcPosts/{ugcPostUrn}", description="Delete a post"),
        EndpointDef(method="GET", path="/connections", description="Get first-degree connections"),
        EndpointDef(method="GET", path="/organizationalEntityAcls", description="List organizations the member is an admin of"),
        EndpointDef(method="POST", path="/assets?action=registerUpload", description="Register a media upload"),
    ]
    
    usage_instructions = (
        "Authenticate via OAuth 2.0 authorization code grant. "
        "Bearer token is injected automatically via the Authorization header. "
        "Use the IntegrationClient to make requests to the base_url + endpoint path. "
        "LinkedIn API v2 uses URN-based identifiers (e.g., urn:li:person:xxx)."
    )
