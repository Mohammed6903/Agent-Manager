from .google_flow import GoogleOAuth2Flow
from .twitter_flow import TwitterOAuth2Flow
from .linkedin_flow import LinkedInOAuth2Flow
from .oauth2_flow import OAuth2FlowProvider

OAUTH2_PROVIDERS: dict[str, OAuth2FlowProvider] = {
    "google": GoogleOAuth2Flow(),
    "twitter": TwitterOAuth2Flow(),
    "linkedin": LinkedInOAuth2Flow(),
}

def get_oauth2_provider(provider_name: str) -> OAuth2FlowProvider:
    provider = OAUTH2_PROVIDERS.get(provider_name)
    if not provider:
        raise KeyError(f"No OAuth2 provider registered for: {provider_name}")
    return provider
