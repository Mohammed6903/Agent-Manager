from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class MicrosoftTeamsIntegration(BaseHTTPIntegration):
    """Microsoft Teams API Integration using Microsoft OAuth 2.0 (Graph API)."""

    name = "microsoft_teams"
    display_name = "Microsoft Teams"
    is_active = False
    test_connection = ("GET", "/me")
    api_type = "rest"
    base_url = "https://graph.microsoft.com/v1.0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import MICROSOFT_TEAMS_OAUTH_FLOW
    oauth2_provider = MICROSOFT_TEAMS_OAUTH_FLOW

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
        EndpointDef(method="GET", path="/me/joinedTeams", description="List teams the user has joined"),
        EndpointDef(method="GET", path="/teams/{team_id}", description="Get a team"),
        EndpointDef(method="GET", path="/teams/{team_id}/channels", description="List channels in a team"),
        EndpointDef(method="GET", path="/teams/{team_id}/channels/{channel_id}", description="Get a channel"),
        EndpointDef(method="POST", path="/teams/{team_id}/channels", description="Create a channel"),
        EndpointDef(method="GET", path="/teams/{team_id}/channels/{channel_id}/messages", description="List messages in a channel"),
        EndpointDef(method="POST", path="/teams/{team_id}/channels/{channel_id}/messages", description="Send a message to a channel"),
        EndpointDef(method="GET", path="/me/chats", description="List chats"),
        EndpointDef(method="GET", path="/me/chats/{chat_id}/messages", description="List messages in a chat"),
        EndpointDef(method="POST", path="/me/chats/{chat_id}/messages", description="Send a message in a chat"),
        EndpointDef(method="GET", path="/teams/{team_id}/members", description="List team members"),
    ]

    usage_instructions = (
        "Microsoft Teams API integration via Microsoft OAuth 2.0 (Graph API). Users sign in with their Microsoft account. Use GET /me/joinedTeams to list teams. POST /teams/{id}/channels/{id}/messages to send channel messages. GET /me/chats for direct messages."
    )
