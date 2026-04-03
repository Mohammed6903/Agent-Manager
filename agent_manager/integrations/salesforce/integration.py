from typing import Dict, List, Any, ClassVar

from ..base import BaseHTTPIntegration, AuthFieldDef, EndpointDef, AuthFlowType, MetadataFieldDef, MetadataFieldType


class SalesforceIntegration(BaseHTTPIntegration):
    """Salesforce API Integration using OAuth 2.0."""

    name = "salesforce"
    display_name = "Salesforce"
    api_type = "rest"
    base_url = "https://{instance_url}/services/data/v59.0"

    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.OAUTH2_GENERIC

    from ..auth.oauth2_configs import SALESFORCE_OAUTH_FLOW
    oauth2_provider = SALESFORCE_OAUTH_FLOW

    auth_scheme: Dict[str, Any] = {
        "type": "oauth2_http",
        "token_field": "access_token",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
    }

    auth_fields: List[AuthFieldDef] = []

    metadata_fields: ClassVar[List[MetadataFieldDef]] = [
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/sobjects", description="List all SObjects (object types)"),
        EndpointDef(method="GET", path="/sobjects/{sobject_type}", description="Describe an SObject"),
        EndpointDef(method="GET", path="/sobjects/{sobject_type}/{record_id}", description="Get a record"),
        EndpointDef(method="POST", path="/sobjects/{sobject_type}", description="Create a record"),
        EndpointDef(method="PATCH", path="/sobjects/{sobject_type}/{record_id}", description="Update a record"),
        EndpointDef(method="DELETE", path="/sobjects/{sobject_type}/{record_id}", description="Delete a record"),
        EndpointDef(method="GET", path="/query", description="Execute a SOQL query"),
        EndpointDef(method="GET", path="/search", description="Execute a SOSL search"),
    ]

    usage_instructions = (
        "Salesforce API integration via OAuth 2.0. Users authorize your app to access their Salesforce org. Use GET /query?q=SELECT... for SOQL queries. CRUD via /sobjects/{type}/{id}."
    )
