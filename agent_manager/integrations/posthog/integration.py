from typing import Dict, List, Any

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class PostHogIntegration(BaseHTTPIntegration):
    """PostHog API Integration."""

    name = "posthog"
    display_name = "PostHog"
    is_active = False
    test_connection = ("GET", "/projects/")
    api_type = "rest"
    base_url = "https://app.posthog.com/api"

    auth_scheme: Dict[str, Any] = {
        "type": "bearer",
        "token_field": "api_key",
    }

    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="api_key", label="PostHog API Key / Auth Token", required=True),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/projects/", description="List projects"),
        EndpointDef(method="GET", path="/projects/{project_id}/insights/", description="List insights (saved queries)"),
        EndpointDef(method="POST", path="/projects/{project_id}/insights/", description="Create an insight"),
        EndpointDef(method="GET", path="/projects/{project_id}/events/", description="List events"),
        EndpointDef(method="GET", path="/projects/{project_id}/persons/", description="List persons"),
        EndpointDef(method="GET", path="/projects/{project_id}/feature_flags/", description="List feature flags"),
        EndpointDef(method="POST", path="/projects/{project_id}/feature_flags/", description="Create a feature flag"),
        EndpointDef(method="PATCH", path="/projects/{project_id}/feature_flags/{flag_id}/", description="Update a feature flag"),
        EndpointDef(method="GET", path="/projects/{project_id}/dashboards/", description="List dashboards"),
        EndpointDef(method="POST", path="/projects/{project_id}/query/", description="Execute a HogQL query"),
    ]

    usage_instructions = (
        "PostHog API integration. Authenticate with Personal API Key (bearer). Use GET /projects/{id}/events/ to list events. POST /projects/{id}/query/ for HogQL queries. GET /projects/{id}/feature_flags/ to manage flags."
    )
