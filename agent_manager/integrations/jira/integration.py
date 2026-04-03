from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class JiraIntegration(BaseHTTPIntegration):
    """Jira API Integration using OAuth 2.0."""

    name = "jira"
    display_name = "Jira"
    api_type = "rest"
    base_url = "https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import JIRA_OAUTH_FLOW
    oauth2_provider = JIRA_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://auth.atlassian.com/oauth/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/myself", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/search", description="Search issues with JQL"),
        EndpointDef(method="GET", path="/issue/{issue_id_or_key}", description="Get an issue"),
        EndpointDef(method="POST", path="/issue", description="Create an issue"),
        EndpointDef(method="PUT", path="/issue/{issue_id_or_key}", description="Update an issue"),
        EndpointDef(method="DELETE", path="/issue/{issue_id_or_key}", description="Delete an issue"),
        EndpointDef(method="POST", path="/issue/{issue_id_or_key}/transitions", description="Transition an issue"),
        EndpointDef(method="GET", path="/project", description="List projects"),
        EndpointDef(method="GET", path="/project/{project_id_or_key}", description="Get a project"),
        EndpointDef(method="GET", path="/issue/{issue_id_or_key}/comment", description="List comments on an issue"),
        EndpointDef(method="POST", path="/issue/{issue_id_or_key}/comment", description="Add a comment to an issue"),
    ]

    usage_instructions = (
        "Jira API integration via Atlassian OAuth 2.0 (3LO). Users authorize access to their Jira Cloud instance. Use GET /search?jql=... to search issues. POST /issue to create issues with {'fields': {...}}."
    )
