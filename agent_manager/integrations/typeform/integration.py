from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class TypeformIntegration(BaseHTTPIntegration):
    """Typeform API Integration using OAuth 2.0."""

    name = "typeform"
    display_name = "Typeform"
    api_type = "rest"
    base_url = "https://api.typeform.com"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import TYPEFORM_OAUTH_FLOW
    oauth2_provider = TYPEFORM_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://api.typeform.com/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/forms", description="List forms"),
        EndpointDef(method="GET", path="/forms/{form_id}", description="Get a form"),
        EndpointDef(method="POST", path="/forms", description="Create a form"),
        EndpointDef(method="PUT", path="/forms/{form_id}", description="Update a form"),
        EndpointDef(method="DELETE", path="/forms/{form_id}", description="Delete a form"),
        EndpointDef(method="GET", path="/forms/{form_id}/responses", description="List responses for a form"),
        EndpointDef(method="GET", path="/workspaces", description="List workspaces"),
        EndpointDef(method="GET", path="/workspaces/{workspace_id}", description="Get a workspace"),
    ]

    usage_instructions = (
        "Typeform API integration via OAuth 2.0. Users allow your app to read/create forms. "
        "Bearer token is injected automatically. "
        "Use GET /forms to list forms. GET /forms/{form_id}/responses for submissions."
    )
