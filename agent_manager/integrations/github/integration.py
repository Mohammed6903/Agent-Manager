from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class GitHubIntegration(BaseHTTPIntegration):
    """GitHub API Integration using OAuth 2.0."""

    name = "github"
    display_name = "GitHub"
    api_type = "rest"
    base_url = "https://api.github.com"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import GITHUB_OAUTH_FLOW
    oauth2_provider = GITHUB_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://github.com/login/oauth/access_token",
        "extra_headers": {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/user", description="Get the authenticated user"),
        EndpointDef(method="GET", path="/user/repos", description="List repositories for the authenticated user"),
        EndpointDef(method="GET", path="/repos/{owner}/{repo}", description="Get a repository"),
        EndpointDef(method="POST", path="/user/repos", description="Create a repository"),
        EndpointDef(method="GET", path="/repos/{owner}/{repo}/issues", description="List issues for a repository"),
        EndpointDef(method="GET", path="/repos/{owner}/{repo}/issues/{issue_number}", description="Get an issue"),
        EndpointDef(method="POST", path="/repos/{owner}/{repo}/issues", description="Create an issue"),
        EndpointDef(method="PATCH", path="/repos/{owner}/{repo}/issues/{issue_number}", description="Update an issue"),
        EndpointDef(method="GET", path="/repos/{owner}/{repo}/pulls", description="List pull requests"),
        EndpointDef(method="GET", path="/repos/{owner}/{repo}/pulls/{pull_number}", description="Get a pull request"),
        EndpointDef(method="POST", path="/repos/{owner}/{repo}/pulls", description="Create a pull request"),
        EndpointDef(method="GET", path="/search/repositories", description="Search repositories"),
        EndpointDef(method="GET", path="/search/issues", description="Search issues and pull requests"),
        EndpointDef(method="GET", path="/search/code", description="Search code"),
    ]

    usage_instructions = (
        "GitHub API integration. Users install your GitHub App via OAuth to grant repo access. "
        "Bearer token is injected automatically. "
        "Use GET /user/repos to list repos. POST /repos/{owner}/{repo}/issues to create issues. "
        "Pagination uses Link headers."
    )
