from typing import Dict, List, Any

from .base import BaseSDKIntegration, AuthFieldDef, EndpointDef, AuthFlowType


class TwitterIntegration(BaseSDKIntegration):
    """Twitter / X API Integration using OAuth 1.0a user context auth."""
    
    name = "twitter"
    display_name = "Twitter / X"
    api_type = "sdk"
    base_url = "https://api.twitter.com/2"
    
    auth_scheme: Dict[str, Any] = {
        "type": "oauth1",
        "consumer_key_field": "api_key",
        "consumer_secret_field": "api_secret",
        "token_field": "access_token",
        "token_secret_field": "access_token_secret",
    }
    
    auth_flow = AuthFlowType.OAUTH1_TWITTER
    
    from .auth.twitter_flow import TwitterOAuth1Flow
    oauth2_provider = TwitterOAuth1Flow()
    
    auth_fields: List[AuthFieldDef] = []
    
    endpoints: List[EndpointDef] = [
        EndpointDef(method="POST", path="/tweets", description="Create a tweet"),
        EndpointDef(method="DELETE", path="/tweets/{id}", description="Delete a tweet"),
        EndpointDef(method="GET", path="/users/me", description="Get authenticated user info"),
        EndpointDef(method="GET", path="/users/{id}", description="Get user by ID"),
        EndpointDef(method="GET", path="/users/by/username/{username}", description="Get user by username"),
        EndpointDef(method="GET", path="/users/{id}/tweets", description="Get a user's tweets"),
        EndpointDef(method="GET", path="/users/{id}/mentions", description="Get a user's mentions"),
        EndpointDef(method="GET", path="/tweets/search/recent", description="Search recent tweets"),
        EndpointDef(method="GET", path="/users/{id}/followers", description="Get a user's followers"),
        EndpointDef(method="GET", path="/users/{id}/following", description="Get users a user is following"),
        EndpointDef(method="GET", path="/dm_conversations/with/{participant_id}/dm_events", description="Get DM events with a user"),
        EndpointDef(method="POST", path="/dm_conversations/with/{participant_id}/messages", description="Send a direct message"),
    ]
    
    usage_instructions = (
        "Authenticate via OAuth 1.0a. "
        "Use the Twitter API v2 endpoints. OAuth 1.0a credentials are used for the Authorization header. "
        "Use the IntegrationClient to make requests to the base_url + endpoint path."
    )
