from .base import BaseAuthHandler
from .bearer import BearerAuthHandler
from .api_key import ApiKeyHeaderHandler, ApiKeyQueryHandler
from .basic import BasicAuthHandler
from .oauth1 import OAuth1Handler
from .oauth2 import OAuth2Handler

AUTH_HANDLERS = {
    "bearer": BearerAuthHandler,
    "api_key_header": ApiKeyHeaderHandler,
    "api_key_query": ApiKeyQueryHandler,
    "basic": BasicAuthHandler,
    "oauth1": OAuth1Handler,
    "oauth2_http": OAuth2Handler,
}

def get_auth_handler(scheme: dict) -> BaseAuthHandler:
    """Instantiate the correct Auth Handler for a given integration's scheme."""
    scheme_type = scheme.get("type")
    
    # Specific edge case to skip fetching handler for Google SDK
    # Google SDK handles its own auth completely.
    if scheme_type == "google_oauth2":
        return None
        
    handler_class = AUTH_HANDLERS.get(scheme_type)
    if not handler_class:
        raise ValueError(f"Unknown auth scheme type: {scheme_type}")
        
    return handler_class(scheme)
