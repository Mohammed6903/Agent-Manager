from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class MailchimpIntegration(BaseHTTPIntegration):
    """Mailchimp API Integration using OAuth 2.0."""

    name = "mailchimp"
    display_name = "Mailchimp"
    api_type = "rest"
    base_url = "https://{dc}.api.mailchimp.com/3.0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import MAILCHIMP_OAUTH_FLOW
    oauth2_provider = MAILCHIMP_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://login.mailchimp.com/oauth2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/lists", description="List audiences (lists)"),
        EndpointDef(method="GET", path="/lists/{list_id}", description="Get an audience"),
        EndpointDef(method="POST", path="/lists", description="Create an audience"),
        EndpointDef(method="GET", path="/lists/{list_id}/members", description="List members in an audience"),
        EndpointDef(method="GET", path="/lists/{list_id}/members/{subscriber_hash}", description="Get a member"),
        EndpointDef(method="POST", path="/lists/{list_id}/members", description="Add a member to an audience"),
        EndpointDef(method="PATCH", path="/lists/{list_id}/members/{subscriber_hash}", description="Update a member"),
        EndpointDef(method="GET", path="/campaigns", description="List campaigns"),
        EndpointDef(method="GET", path="/campaigns/{campaign_id}", description="Get a campaign"),
        EndpointDef(method="POST", path="/campaigns", description="Create a campaign"),
        EndpointDef(method="POST", path="/campaigns/{campaign_id}/actions/send", description="Send a campaign"),
    ]

    usage_instructions = (
        "Mailchimp API integration via OAuth 2.0. Users authorize access to their Mailchimp account. Use GET /lists to list audiences. POST /lists/{id}/members to add subscribers. POST /campaigns to create campaigns."
    )
