from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleAnalyticsIntegration(BaseGoogleIntegration):
    """Integration definition for Google Analytics Data API (GA4)."""

    name = "google_analytics"
    display_name = "Google Analytics"
    test_connection = ("GET", "analytics/v1beta/properties")
    is_active = False
    base_url = "https://analyticsdata.googleapis.com/v1beta"

    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/analytics.readonly",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/properties/{property_id}:runReport", description="Run a report (dimensions, metrics, date ranges)"),
        EndpointDef(method="POST", path="/properties/{property_id}:runRealtimeReport", description="Run a realtime report"),
        EndpointDef(method="POST", path="/properties/{property_id}:batchRunReports", description="Run multiple reports in one request"),
        EndpointDef(method="GET", path="/properties/{property_id}/metadata", description="Get available dimensions and metrics"),
    ]

    usage_instructions = (
        "Google Analytics Data API (GA4). Use POST /properties/{id}:runReport with "
        "{dimensions, metrics, dateRanges} to query analytics data. "
        "POST :runRealtimeReport for live data. GET /properties/{id}/metadata for available fields."
    )
