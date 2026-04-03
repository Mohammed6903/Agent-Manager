from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class PipedriveIntegration(BaseHTTPIntegration):
    """Pipedrive API Integration using OAuth 2.0."""

    name = "pipedrive"
    display_name = "Pipedrive"
    api_type = "rest"
    base_url = "https://api.pipedrive.com/v1"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import PIPEDRIVE_OAUTH_FLOW
    oauth2_provider = PIPEDRIVE_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://oauth.pipedrive.com/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/deals", description="List deals"),
        EndpointDef(method="GET", path="/deals/{id}", description="Get a deal"),
        EndpointDef(method="POST", path="/deals", description="Create a deal"),
        EndpointDef(method="PUT", path="/deals/{id}", description="Update a deal"),
        EndpointDef(method="DELETE", path="/deals/{id}", description="Delete a deal"),
        EndpointDef(method="GET", path="/persons", description="List persons (contacts)"),
        EndpointDef(method="GET", path="/persons/{id}", description="Get a person"),
        EndpointDef(method="POST", path="/persons", description="Create a person"),
        EndpointDef(method="PUT", path="/persons/{id}", description="Update a person"),
        EndpointDef(method="GET", path="/organizations", description="List organizations"),
        EndpointDef(method="GET", path="/organizations/{id}", description="Get an organization"),
        EndpointDef(method="POST", path="/organizations", description="Create an organization"),
        EndpointDef(method="GET", path="/activities", description="List activities"),
        EndpointDef(method="POST", path="/activities", description="Create an activity"),
        EndpointDef(method="GET", path="/pipelines", description="List pipelines"),
        EndpointDef(method="GET", path="/stages", description="List stages"),
    ]

    usage_instructions = (
        "Pipedrive API integration via OAuth 2.0. Users authorize access to their sales CRM. Use GET /deals to list deals. POST /deals to create. GET /persons for contacts. GET /pipelines for pipeline overview."
    )
