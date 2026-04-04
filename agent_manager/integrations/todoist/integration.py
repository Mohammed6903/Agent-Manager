from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType


class TodoistIntegration(BaseHTTPIntegration):
    """Todoist REST API Integration using OAuth 2.0."""

    name = "todoist"
    display_name = "Todoist"
    is_active = False
    test_connection = ("GET", "/projects")
    api_type = "rest"
    base_url = "https://api.todoist.com/rest/v2"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import TODOIST_OAUTH_FLOW
    oauth2_provider = TODOIST_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://todoist.com/oauth/access_token",
    }

    auth_fields: List[AuthFieldDef] = []

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/projects", description="List all projects"),
        EndpointDef(method="GET", path="/projects/{project_id}", description="Get a project"),
        EndpointDef(method="POST", path="/projects", description="Create a project"),
        EndpointDef(method="POST", path="/projects/{project_id}", description="Update a project"),
        EndpointDef(method="DELETE", path="/projects/{project_id}", description="Delete a project"),
        EndpointDef(method="GET", path="/tasks", description="List active tasks"),
        EndpointDef(method="GET", path="/tasks/{task_id}", description="Get a task"),
        EndpointDef(method="POST", path="/tasks", description="Create a task"),
        EndpointDef(method="POST", path="/tasks/{task_id}", description="Update a task"),
        EndpointDef(method="POST", path="/tasks/{task_id}/close", description="Close (complete) a task"),
        EndpointDef(method="POST", path="/tasks/{task_id}/reopen", description="Reopen a task"),
        EndpointDef(method="DELETE", path="/tasks/{task_id}", description="Delete a task"),
        EndpointDef(method="GET", path="/comments", description="List comments for a task or project"),
        EndpointDef(method="POST", path="/comments", description="Create a comment"),
        EndpointDef(method="GET", path="/labels", description="List all personal labels"),
        EndpointDef(method="POST", path="/labels", description="Create a label"),
        EndpointDef(method="GET", path="/sections", description="List sections"),
        EndpointDef(method="POST", path="/sections", description="Create a section"),
    ]

    usage_instructions = (
        "Todoist API integration via OAuth 2.0. Users grant permission to view and modify tasks. "
        "Bearer token is injected automatically. "
        "Use POST /tasks to create tasks (requires 'content' field). "
        "Use POST /tasks/{id}/close to complete a task."
    )
