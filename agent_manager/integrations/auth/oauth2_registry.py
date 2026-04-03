from agent_manager.integrations.google.auth.flow import GoogleOAuth2Flow
from agent_manager.integrations.twitter.flow import TwitterOAuth2Flow
from agent_manager.integrations.linkedin.flow import LinkedInOAuth2Flow
from agent_manager.integrations.stripe.flow import StripeConnectOAuth2Flow
from agent_manager.integrations.notion.flow import NotionOAuth2Flow
from .oauth2_flow import OAuth2FlowProvider
from .oauth2_configs import (
    SLACK_OAUTH_FLOW,
    GITHUB_OAUTH_FLOW,
    TRELLO_OAUTH_FLOW,
    AIRTABLE_OAUTH_FLOW,
    ASANA_OAUTH_FLOW,
    CLICKUP_OAUTH_FLOW,
    TODOIST_OAUTH_FLOW,
    TYPEFORM_OAUTH_FLOW,
    HUBSPOT_OAUTH_FLOW,
    JIRA_OAUTH_FLOW,
    SALESFORCE_OAUTH_FLOW,
    MONDAY_OAUTH_FLOW,
    DROPBOX_OAUTH_FLOW,
    MAILCHIMP_OAUTH_FLOW,
    CALENDLY_OAUTH_FLOW,
    PIPEDRIVE_OAUTH_FLOW,
    CONFLUENCE_OAUTH_FLOW,
    ZOHO_CRM_OAUTH_FLOW,
    LINEAR_OAUTH_FLOW,
    BOX_OAUTH_FLOW,
    BUFFER_OAUTH_FLOW,
    WRIKE_OAUTH_FLOW,
    EVENTBRITE_OAUTH_FLOW,
    BASECAMP_OAUTH_FLOW,
    QUICKBOOKS_OAUTH_FLOW,
    XERO_OAUTH_FLOW,
    WORDPRESS_OAUTH_FLOW,
    SQUARE_OAUTH_FLOW,
    OUTLOOK_OAUTH_FLOW,
    MICROSOFT_TEAMS_OAUTH_FLOW,
    ONEDRIVE_OAUTH_FLOW,
)

OAUTH2_PROVIDERS: dict[str, OAuth2FlowProvider] = {
    "google": GoogleOAuth2Flow(),
    "twitter": TwitterOAuth2Flow(),
    "linkedin": LinkedInOAuth2Flow(),
    "slack": SLACK_OAUTH_FLOW,
    "github": GITHUB_OAUTH_FLOW,
    "trello": TRELLO_OAUTH_FLOW,
    "airtable": AIRTABLE_OAUTH_FLOW,
    "asana": ASANA_OAUTH_FLOW,
    "clickup": CLICKUP_OAUTH_FLOW,
    "todoist": TODOIST_OAUTH_FLOW,
    "typeform": TYPEFORM_OAUTH_FLOW,
    "hubspot": HUBSPOT_OAUTH_FLOW,
    "stripe": StripeConnectOAuth2Flow(),
    "notion": NotionOAuth2Flow(),
    "jira": JIRA_OAUTH_FLOW,
    "salesforce": SALESFORCE_OAUTH_FLOW,
    "monday": MONDAY_OAUTH_FLOW,
    "dropbox": DROPBOX_OAUTH_FLOW,
    "mailchimp": MAILCHIMP_OAUTH_FLOW,
    "calendly": CALENDLY_OAUTH_FLOW,
    "pipedrive": PIPEDRIVE_OAUTH_FLOW,
    "confluence": CONFLUENCE_OAUTH_FLOW,
    "zohocrm": ZOHO_CRM_OAUTH_FLOW,
    "linear": LINEAR_OAUTH_FLOW,
    "box": BOX_OAUTH_FLOW,
    "buffer": BUFFER_OAUTH_FLOW,
    "wrike": WRIKE_OAUTH_FLOW,
    "eventbrite": EVENTBRITE_OAUTH_FLOW,
    "basecamp": BASECAMP_OAUTH_FLOW,
    "quickbooks": QUICKBOOKS_OAUTH_FLOW,
    "xero": XERO_OAUTH_FLOW,
    "wordpress": WORDPRESS_OAUTH_FLOW,
    "square": SQUARE_OAUTH_FLOW,
    "outlook": OUTLOOK_OAUTH_FLOW,
    "microsoft_teams": MICROSOFT_TEAMS_OAUTH_FLOW,
    "onedrive": ONEDRIVE_OAUTH_FLOW,
}

def get_oauth2_provider(provider_name: str) -> OAuth2FlowProvider:
    provider = OAUTH2_PROVIDERS.get(provider_name)
    if not provider:
        raise KeyError(f"No OAuth2 provider registered for: {provider_name}")
    return provider
