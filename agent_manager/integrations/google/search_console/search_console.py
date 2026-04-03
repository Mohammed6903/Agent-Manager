from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleSearchConsoleIntegration(BaseGoogleIntegration):
    """Integration definition for Google Search Console API."""

    name = "google_search_console"
    display_name = "Google Search Console"
    base_url = "https://searchconsole.googleapis.com/v1"

    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/webmasters.readonly",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/sites", description="List verified sites"),
        EndpointDef(method="GET", path="/sites/{site_url}", description="Get a site"),
        EndpointDef(method="POST", path="/sites/{site_url}/searchAnalytics/query", description="Query search analytics data (clicks, impressions, CTR, position)"),
        EndpointDef(method="GET", path="/sites/{site_url}/sitemaps", description="List sitemaps"),
        EndpointDef(method="POST", path="/sites/{site_url}/urlInspection/index:inspect", description="Inspect a URL's index status"),
    ]

    usage_instructions = (
        "Google Search Console API. Use GET /sites to list verified properties. "
        "POST /sites/{url}/searchAnalytics/query with {startDate, endDate, dimensions} "
        "to get search performance data (clicks, impressions, CTR, position). "
        "POST .../urlInspection/index:inspect to check indexing status."
    )
