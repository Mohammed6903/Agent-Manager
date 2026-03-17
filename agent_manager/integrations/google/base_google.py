from typing import Dict, Any, List

from ..base import BaseSDKIntegration
from agent_manager.integrations.google.auth.flow import GoogleOAuth2Flow
from ..base import AuthFlowType


class BaseGoogleIntegration(BaseSDKIntegration):
    """Base class for all Google workspace integrations using OAuth2 flow."""
    
    api_type = "oauth2_google"
    auth_flow = AuthFlowType.OAUTH2_GOOGLE
    oauth2_provider = GoogleOAuth2Flow()
    auth_scheme: Dict[str, Any] = {"type": "google_oauth2"}
    auth_fields: List[Any] = []
    scopes: List[str] = []
