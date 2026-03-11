from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any, ClassVar, Optional
from pydantic import BaseModel, ConfigDict
from enum import Enum


class AuthFlowType(str, Enum):
    STATIC = "static"          # API keys, bearer tokens — user provides directly
    OAUTH2_GOOGLE = "oauth2_google"    # Google OAuth — handled by GoogleOAuth2Flow
    OAUTH2_GENERIC = "oauth2_generic"  # Future OAuth providers, List, Any
    OAUTH1_TWITTER = "oauth1_twitter"  # Twitter OAuth 1.0a
    OAUTH2_LINKEDIN = "oauth2_linkedin"  # LinkedIn OAuth 2.0


class MetadataFieldType(str, Enum):
    STRING = "string"
    IMAGE_URL = "image_url"


@dataclass
class MetadataFieldDef:
    """Declares a single whitelisted metadata field and how the UI should render it."""
    name: str
    type: MetadataFieldType = MetadataFieldType.STRING


@dataclass
class AuthFieldDef:
    name: str
    label: str
    required: bool


@dataclass
class EndpointDef:
    method: str
    path: str
    description: str


class BaseIntegration:
    """Abstract base class for hardcoded integrations."""
    name: str
    display_name: str
    api_type: str = "rest"
    base_url: str
    auth_scheme: Dict[str, Any]
    auth_fields: List[AuthFieldDef]
    endpoints: List[EndpointDef]
    usage_instructions: ClassVar[str] = ""
    auth_flow: ClassVar[AuthFlowType] = AuthFlowType.STATIC
    oauth2_provider: ClassVar[Optional["OAuth2FlowProvider"]] = None
    # Whitelisted metadata fields surfaced in API responses.
    # Each entry declares the field name and how the UI should render the value.
    # Override per integration — default exposes nothing.
    metadata_fields: ClassVar[List[MetadataFieldDef]] = []

    @classmethod
    def filter_metadata(cls, raw: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Return a typed list of metadata entries from raw integration_metadata.

        Each item is {"key": ..., "value": ..., "type": ...} so the frontend
        can render strings and images differently without guessing.
        Returns None when raw is None or no fields are whitelisted.
        """
        if not raw or not cls.metadata_fields:
            return None
        result = [
            {"key": f.name, "value": raw[f.name], "type": f.type.value}
            for f in cls.metadata_fields
            if f.name in raw
        ]
        return result or None

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Serialize the integration definition for API responses."""
        return {
            "name": cls.name,
            "display_name": getattr(cls, "display_name", cls.name),
            "api_type": cls.api_type,
            "base_url": getattr(cls, "base_url", ""),
            "auth_scheme": getattr(cls, "auth_scheme", {}),
            "auth_fields": [
                {"name": f.name, "label": f.label, "required": f.required}
                for f in getattr(cls, "auth_fields", [])
            ],
            "endpoints": [
                {"method": e.method, "path": e.path, "description": e.description}
                for e in getattr(cls, "endpoints", [])
            ],
            "usage_instructions": getattr(cls, "usage_instructions", ""),
        }

class BaseHTTPIntegration(BaseIntegration):
    """Marker class for standard integrations using IntegrationClient over HTTP."""
    api_type: str = "rest"
    
class BaseSDKIntegration(BaseIntegration):
    """Marker class for integrations handled by SDKs with decorator-based logging."""
    api_type: str = "sdk"
    auth_fields: List[AuthFieldDef] = []
