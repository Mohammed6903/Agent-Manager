from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class TrelloIntegration(BaseHTTPIntegration):
    """Trello API Integration using Atlassian OAuth 2.0 (3LO)."""

    name = "trello"
    display_name = "Trello"
    is_active = False
    test_connection = ("GET", "/members/me")
    api_type = "rest"
    base_url = "https://api.trello.com/1"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import TRELLO_OAUTH_FLOW
    oauth2_provider = TRELLO_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://auth.atlassian.com/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/members/me/boards", description="List boards for the authenticated member"),
        EndpointDef(method="GET", path="/boards/{board_id}", description="Get a board"),
        EndpointDef(method="POST", path="/boards", description="Create a new board"),
        EndpointDef(method="GET", path="/boards/{board_id}/lists", description="Get lists on a board"),
        EndpointDef(method="POST", path="/lists", description="Create a new list"),
        EndpointDef(method="PUT", path="/lists/{list_id}", description="Update a list"),
        EndpointDef(method="GET", path="/lists/{list_id}/cards", description="Get cards on a list"),
        EndpointDef(method="GET", path="/cards/{card_id}", description="Get a card"),
        EndpointDef(method="POST", path="/cards", description="Create a new card"),
        EndpointDef(method="PUT", path="/cards/{card_id}", description="Update a card"),
        EndpointDef(method="DELETE", path="/cards/{card_id}", description="Delete a card"),
        EndpointDef(method="GET", path="/members/me", description="Get the authenticated member"),
        EndpointDef(method="GET", path="/boards/{board_id}/labels", description="Get labels on a board"),
        EndpointDef(method="POST", path="/checklists", description="Create a checklist"),
        EndpointDef(method="GET", path="/cards/{card_id}/checklists", description="Get checklists on a card"),
    ]

    usage_instructions = (
        "Trello API integration via Atlassian OAuth 2.0. "
        "Users authorize via Atlassian/Trello prompt to grant board access. "
        "Bearer token is injected automatically. "
        "Use GET /members/me/boards to list boards. POST /cards to create cards."
    )
