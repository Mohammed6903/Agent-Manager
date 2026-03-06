from typing import Dict, List, Any

from .base import BaseHTTPIntegration, AuthFieldDef, EndpointDef


class NotionIntegration(BaseHTTPIntegration):
    """Notion API Integration using hardcoded credentials map."""
    
    name = "notion"
    display_name = "Notion"
    api_type = "rest"
    base_url = "https://api.notion.com/v1"
    
    auth_scheme: Dict[str, Any] = {
        "type": "bearer",
        "token_field": "bot_token",
        "extra_headers": {
            "Notion-Version": "{api_version}"
        }
    }
    
    auth_fields: List[AuthFieldDef] = [
        AuthFieldDef(name="bot_token", label="Internal Integration Token", required=True),
        AuthFieldDef(name="api_version", label="Notion API Version (e.g., 2022-06-28)", required=False)
    ]
    
    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/search", description="Search all pages in workspace"),
        EndpointDef(method="POST", path="/pages", description="Create a new page"),
        EndpointDef(method="GET", path="/users", description="List users"),
    ]
    
    usage_instructions = (
        "Authenticate using Authorization: Bearer {bot_token}. "
        "Also inject Notion-Version header using {api_version} if provided (default 2022-06-28)."
    )
