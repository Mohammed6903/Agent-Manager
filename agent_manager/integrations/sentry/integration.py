from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class SentryIntegration(BaseHTTPIntegration):
    """Sentry API Integration."""

    name = "sentry"
    display_name = "Sentry"
    is_active = False
    test_connection = ("GET", "/organizations/")
    api_type = "rest"
    base_url = "https://sentry.io/api/0"

    auth_scheme: Dict[str, Any] = {
        "type": "bearer",
        "token_field": "api_key",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="api_key", label="Sentry API Key / Auth Token", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/organizations/", description="List organizations"),
        EndpointDef(method="GET", path="/organizations/{org_slug}/projects/", description="List projects"),
        EndpointDef(method="GET", path="/projects/{org_slug}/{project_slug}/issues/", description="List issues"),
        EndpointDef(method="GET", path="/issues/{issue_id}/", description="Get an issue"),
        EndpointDef(method="PUT", path="/issues/{issue_id}/", description="Update an issue (resolve, ignore, etc.)"),
        EndpointDef(method="GET", path="/issues/{issue_id}/events/", description="List events for an issue"),
        EndpointDef(method="GET", path="/issues/{issue_id}/events/latest/", description="Get latest event for an issue"),
        EndpointDef(method="GET", path="/projects/{org_slug}/{project_slug}/stats/", description="Get project stats"),
    ]

    usage_instructions = (
        "Sentry API integration. Authenticate with Auth Token (bearer). Use GET /organizations/ to list orgs. GET /projects/{org}/{proj}/issues/ to list errors. PUT /issues/{id}/ with {status: 'resolved'} to resolve."
    )
