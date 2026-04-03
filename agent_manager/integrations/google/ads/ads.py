from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleAdsIntegration(BaseGoogleIntegration):
    """Integration definition for Google Ads."""

    name = "google_ads"
    display_name = "Google Ads"
    base_url = "https://googleads.googleapis.com/v16"

    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/adwords",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/customers/{customer_id}", description="Get customer (account) details"),
        EndpointDef(method="GET", path="/customers/{customer_id}/campaigns", description="List campaigns"),
        EndpointDef(method="POST", path="/customers/{customer_id}/googleAds:searchStream", description="Execute a Google Ads Query Language (GAQL) query"),
        EndpointDef(method="POST", path="/customers/{customer_id}/campaigns:mutate", description="Create, update, or remove campaigns"),
        EndpointDef(method="POST", path="/customers/{customer_id}/adGroups:mutate", description="Create, update, or remove ad groups"),
        EndpointDef(method="POST", path="/customers/{customer_id}/ads:mutate", description="Create, update, or remove ads"),
        EndpointDef(method="GET", path="/customers:listAccessibleCustomers", description="List accessible customer accounts"),
    ]

    usage_instructions = (
        "Google Ads API. Use POST /customers/{id}/googleAds:searchStream with GAQL queries "
        "to read campaign, ad group, ad, and keyword data. Use :mutate endpoints to create/update resources. "
        "GET /customers:listAccessibleCustomers to discover accounts."
    )
