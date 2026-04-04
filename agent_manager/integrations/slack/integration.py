from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class SlackIntegration(BaseHTTPIntegration):
    """Slack API Integration using OAuth 2.0."""

    name = "slack"
    display_name = "Slack"
    is_active = False
    test_connection = ("POST", "/conversations.list")
    api_type = "rest"
    base_url = "https://slack.com/api"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import SLACK_OAUTH_FLOW
    oauth2_provider = SLACK_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://slack.com/api/oauth.v2.access",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        # Channels
        EndpointDef(method="POST", path="/conversations.list", description="List channels in workspace"),
        EndpointDef(method="POST", path="/conversations.info", description="Get info about a channel"),
        EndpointDef(method="POST", path="/conversations.create", description="Create a new channel"),
        EndpointDef(method="POST", path="/conversations.history", description="Get message history of a channel"),
        # Messages
        EndpointDef(method="POST", path="/chat.postMessage", description="Send a message to a channel"),
        EndpointDef(method="POST", path="/chat.update", description="Update an existing message"),
        EndpointDef(method="POST", path="/chat.delete", description="Delete a message"),
        # Users
        EndpointDef(method="POST", path="/users.list", description="List all users in workspace"),
        EndpointDef(method="POST", path="/users.info", description="Get info about a user"),
        # Reactions
        EndpointDef(method="POST", path="/reactions.add", description="Add a reaction to a message"),
        EndpointDef(method="POST", path="/reactions.remove", description="Remove a reaction from a message"),
        # Files
        EndpointDef(method="POST", path="/files.list", description="List files shared in the workspace"),
    ]

    usage_instructions = (
        "Slack API integration. Connects via OAuth 2.0 — users click 'Add to Slack' to authorize. "
        "Bearer token is injected automatically. "
        "Use /chat.postMessage to send messages (requires 'channel' and 'text' fields). "
        "Use /conversations.list to discover channels. "
        "All responses include an 'ok' boolean indicating success."
    )
