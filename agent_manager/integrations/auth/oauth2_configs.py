"""OAuth 2.0 configurations for all third-party integrations.

Each config defines the provider's authorize/token URLs, scopes, and
settings attribute names for client credentials. The GenericOAuth2Flow
class uses these to drive the full authorization code grant.
"""

from .generic_oauth2_flow import GenericOAuth2Config, GenericOAuth2Flow


# ── Slack ─────────────────────────────────────────────────────────────────────
SLACK_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="slack",
    authorize_url="https://slack.com/oauth/v2/authorize",
    token_url="https://slack.com/api/oauth.v2.access",
    client_id_setting="SLACK_CLIENT_ID",
    client_secret_setting="SLACK_CLIENT_SECRET",
    scopes=[
        "channels:read", "channels:history", "channels:manage",
        "chat:write", "users:read", "reactions:read", "reactions:write",
        "files:read",
    ],
    userinfo_url="https://slack.com/api/auth.test",
)

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="github",
    authorize_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    client_id_setting="GITHUB_CLIENT_ID",
    client_secret_setting="GITHUB_CLIENT_SECRET",
    scopes=["repo", "read:user", "user:email"],
    userinfo_url="https://api.github.com/user",
    userinfo_headers={"Accept": "application/vnd.github+json"},
)

# ── Trello ────────────────────────────────────────────────────────────────────
# Trello uses OAuth 1.0a natively but supports a REST API token auth
# via Atlassian's OAuth 2.0 (3LO) for Power-Ups.
TRELLO_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="trello",
    authorize_url="https://auth.atlassian.com/authorize",
    token_url="https://auth.atlassian.com/oauth/token",
    client_id_setting="TRELLO_CLIENT_ID",
    client_secret_setting="TRELLO_CLIENT_SECRET",
    scopes=["read:trello", "write:trello"],
    extra_authorize_params={
        "audience": "api.atlassian.com",
        "prompt": "consent",
    },
    userinfo_url="https://api.trello.com/1/members/me",
)

# ── Airtable ──────────────────────────────────────────────────────────────────
AIRTABLE_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="airtable",
    authorize_url="https://airtable.com/oauth2/v1/authorize",
    token_url="https://airtable.com/oauth2/v1/token",
    client_id_setting="AIRTABLE_CLIENT_ID",
    client_secret_setting="AIRTABLE_CLIENT_SECRET",
    scopes=[
        "data.records:read", "data.records:write",
        "schema.bases:read",
    ],
    userinfo_url="https://api.airtable.com/v0/meta/whoami",
)

# ── Asana ─────────────────────────────────────────────────────────────────────
ASANA_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="asana",
    authorize_url="https://app.asana.com/-/oauth_authorize",
    token_url="https://app.asana.com/-/oauth_token",
    client_id_setting="ASANA_CLIENT_ID",
    client_secret_setting="ASANA_CLIENT_SECRET",
    scopes=["default"],
    userinfo_url="https://app.asana.com/api/1.0/users/me",
)

# ── ClickUp ───────────────────────────────────────────────────────────────────
CLICKUP_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="clickup",
    authorize_url="https://app.clickup.com/api",
    token_url="https://api.clickup.com/api/v2/oauth/token",
    client_id_setting="CLICKUP_CLIENT_ID",
    client_secret_setting="CLICKUP_CLIENT_SECRET",
    scopes=[],  # ClickUp doesn't use scopes in OAuth
    userinfo_url="https://api.clickup.com/api/v2/user",
)

# ── Todoist ───────────────────────────────────────────────────────────────────
TODOIST_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="todoist",
    authorize_url="https://todoist.com/oauth/authorize",
    token_url="https://todoist.com/oauth/access_token",
    client_id_setting="TODOIST_CLIENT_ID",
    client_secret_setting="TODOIST_CLIENT_SECRET",
    scopes=["data:read_write"],
)

# ── Typeform ──────────────────────────────────────────────────────────────────
TYPEFORM_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="typeform",
    authorize_url="https://api.typeform.com/oauth/authorize",
    token_url="https://api.typeform.com/oauth/token",
    client_id_setting="TYPEFORM_CLIENT_ID",
    client_secret_setting="TYPEFORM_CLIENT_SECRET",
    scopes=[
        "forms:read", "forms:write",
        "responses:read",
        "workspaces:read",
    ],
    userinfo_url="https://api.typeform.com/me",
)

# ── HubSpot ───────────────────────────────────────────────────────────────────
HUBSPOT_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="hubspot",
    authorize_url="https://app.hubspot.com/oauth/authorize",
    token_url="https://api.hubapi.com/oauth/v1/token",
    client_id_setting="HUBSPOT_CLIENT_ID",
    client_secret_setting="HUBSPOT_CLIENT_SECRET",
    scopes=[
        "crm.objects.contacts.read", "crm.objects.contacts.write",
        "crm.objects.companies.read", "crm.objects.companies.write",
        "crm.objects.deals.read", "crm.objects.deals.write",
        "tickets",
    ],
)

# ── Jira ──────────────────────────────────────────────────────────────────────
JIRA_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="jira",
    authorize_url="https://auth.atlassian.com/authorize",
    token_url="https://auth.atlassian.com/oauth/token",
    client_id_setting="JIRA_CLIENT_ID",
    client_secret_setting="JIRA_CLIENT_SECRET",
    scopes=["read:jira-work", "write:jira-work", "read:jira-user", "offline_access"],
    extra_authorize_params={"audience": "api.atlassian.com", "prompt": "consent"},
    userinfo_url="https://api.atlassian.com/me",
)

# ── Salesforce ────────────────────────────────────────────────────────────────
SALESFORCE_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="salesforce",
    authorize_url="https://login.salesforce.com/services/oauth2/authorize",
    token_url="https://login.salesforce.com/services/oauth2/token",
    client_id_setting="SALESFORCE_CLIENT_ID",
    client_secret_setting="SALESFORCE_CLIENT_SECRET",
    scopes=["api", "refresh_token"],
    userinfo_url="https://login.salesforce.com/services/oauth2/userinfo",
)

# ── Monday ────────────────────────────────────────────────────────────────────
MONDAY_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="monday",
    authorize_url="https://auth.monday.com/oauth2/authorize",
    token_url="https://auth.monday.com/oauth2/token",
    client_id_setting="MONDAY_CLIENT_ID",
    client_secret_setting="MONDAY_CLIENT_SECRET",
    scopes=[],
)

# ── Dropbox ───────────────────────────────────────────────────────────────────
DROPBOX_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="dropbox",
    authorize_url="https://www.dropbox.com/oauth2/authorize",
    token_url="https://api.dropboxapi.com/oauth2/token",
    client_id_setting="DROPBOX_CLIENT_ID",
    client_secret_setting="DROPBOX_CLIENT_SECRET",
    scopes=[],
    extra_authorize_params={"token_access_type": "offline"},
)

# ── Mailchimp ─────────────────────────────────────────────────────────────────
MAILCHIMP_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="mailchimp",
    authorize_url="https://login.mailchimp.com/oauth2/authorize",
    token_url="https://login.mailchimp.com/oauth2/token",
    client_id_setting="MAILCHIMP_CLIENT_ID",
    client_secret_setting="MAILCHIMP_CLIENT_SECRET",
    scopes=[],
    userinfo_url="https://login.mailchimp.com/oauth2/metadata",
)

# ── Calendly ──────────────────────────────────────────────────────────────────
CALENDLY_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="calendly",
    authorize_url="https://auth.calendly.com/oauth/authorize",
    token_url="https://auth.calendly.com/oauth/token",
    client_id_setting="CALENDLY_CLIENT_ID",
    client_secret_setting="CALENDLY_CLIENT_SECRET",
    scopes=[],
    userinfo_url="https://api.calendly.com/users/me",
)

# ── Pipedrive ─────────────────────────────────────────────────────────────────
PIPEDRIVE_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="pipedrive",
    authorize_url="https://oauth.pipedrive.com/oauth/authorize",
    token_url="https://oauth.pipedrive.com/oauth/token",
    client_id_setting="PIPEDRIVE_CLIENT_ID",
    client_secret_setting="PIPEDRIVE_CLIENT_SECRET",
    scopes=[],
    userinfo_url="https://api.pipedrive.com/v1/users/me",
)

# ── Confluence ────────────────────────────────────────────────────────────────
CONFLUENCE_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="confluence",
    authorize_url="https://auth.atlassian.com/authorize",
    token_url="https://auth.atlassian.com/oauth/token",
    client_id_setting="CONFLUENCE_CLIENT_ID",
    client_secret_setting="CONFLUENCE_CLIENT_SECRET",
    scopes=["read:confluence-content.all", "write:confluence-content", "read:confluence-user", "offline_access"],
    extra_authorize_params={"audience": "api.atlassian.com", "prompt": "consent"},
    userinfo_url="https://api.atlassian.com/me",
)

# ── Zoho CRM ──────────────────────────────────────────────────────────────────
ZOHO_CRM_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="zohocrm",
    authorize_url="https://accounts.zoho.com/oauth/v2/auth",
    token_url="https://accounts.zoho.com/oauth/v2/token",
    client_id_setting="ZOHO_CRM_CLIENT_ID",
    client_secret_setting="ZOHO_CRM_CLIENT_SECRET",
    scopes=["ZohoCRM.modules.ALL", "ZohoCRM.settings.ALL"],
    extra_authorize_params={"access_type": "offline"},
)


# ── Flow Instances ────────────────────────────────────────────────────────────
# Instantiate GenericOAuth2Flow for each config.
# These are imported by the integration classes and the oauth2_registry.

SLACK_OAUTH_FLOW = GenericOAuth2Flow(SLACK_OAUTH_CONFIG)
GITHUB_OAUTH_FLOW = GenericOAuth2Flow(GITHUB_OAUTH_CONFIG)
TRELLO_OAUTH_FLOW = GenericOAuth2Flow(TRELLO_OAUTH_CONFIG)
AIRTABLE_OAUTH_FLOW = GenericOAuth2Flow(AIRTABLE_OAUTH_CONFIG)
ASANA_OAUTH_FLOW = GenericOAuth2Flow(ASANA_OAUTH_CONFIG)
CLICKUP_OAUTH_FLOW = GenericOAuth2Flow(CLICKUP_OAUTH_CONFIG)
TODOIST_OAUTH_FLOW = GenericOAuth2Flow(TODOIST_OAUTH_CONFIG)
TYPEFORM_OAUTH_FLOW = GenericOAuth2Flow(TYPEFORM_OAUTH_CONFIG)
HUBSPOT_OAUTH_FLOW = GenericOAuth2Flow(HUBSPOT_OAUTH_CONFIG)
JIRA_OAUTH_FLOW = GenericOAuth2Flow(JIRA_OAUTH_CONFIG)
SALESFORCE_OAUTH_FLOW = GenericOAuth2Flow(SALESFORCE_OAUTH_CONFIG)
MONDAY_OAUTH_FLOW = GenericOAuth2Flow(MONDAY_OAUTH_CONFIG)
DROPBOX_OAUTH_FLOW = GenericOAuth2Flow(DROPBOX_OAUTH_CONFIG)
MAILCHIMP_OAUTH_FLOW = GenericOAuth2Flow(MAILCHIMP_OAUTH_CONFIG)
CALENDLY_OAUTH_FLOW = GenericOAuth2Flow(CALENDLY_OAUTH_CONFIG)
PIPEDRIVE_OAUTH_FLOW = GenericOAuth2Flow(PIPEDRIVE_OAUTH_CONFIG)
CONFLUENCE_OAUTH_FLOW = GenericOAuth2Flow(CONFLUENCE_OAUTH_CONFIG)
ZOHO_CRM_OAUTH_FLOW = GenericOAuth2Flow(ZOHO_CRM_OAUTH_CONFIG)

# ── Linear ────────────────────────────────────────────────────────────────────
LINEAR_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="linear",
    authorize_url="https://linear.app/oauth/authorize",
    token_url="https://api.linear.app/oauth/token",
    client_id_setting="LINEAR_CLIENT_ID",
    client_secret_setting="LINEAR_CLIENT_SECRET",
    scopes=["read", "write", "issues:create", "comments:create"],
    userinfo_url="https://api.linear.app/graphql",  # needs POST, handled below
)

# ── Box ───────────────────────────────────────────────────────────────────────
BOX_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="box",
    authorize_url="https://account.box.com/api/oauth2/authorize",
    token_url="https://api.box.com/oauth2/token",
    client_id_setting="BOX_CLIENT_ID",
    client_secret_setting="BOX_CLIENT_SECRET",
    scopes=[],
    userinfo_url="https://api.box.com/2.0/users/me",
)

# ── Buffer ────────────────────────────────────────────────────────────────────
BUFFER_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="buffer",
    authorize_url="https://bufferapp.com/oauth2/authorize",
    token_url="https://api.bufferapp.com/1/oauth2/token.json",
    client_id_setting="BUFFER_CLIENT_ID",
    client_secret_setting="BUFFER_CLIENT_SECRET",
    scopes=[],
    userinfo_url="https://api.bufferapp.com/1/user.json",
)

LINEAR_OAUTH_FLOW = GenericOAuth2Flow(LINEAR_OAUTH_CONFIG)
BOX_OAUTH_FLOW = GenericOAuth2Flow(BOX_OAUTH_CONFIG)
BUFFER_OAUTH_FLOW = GenericOAuth2Flow(BUFFER_OAUTH_CONFIG)

# ── Wrike ─────────────────────────────────────────────────────────────────────
WRIKE_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="wrike",
    authorize_url="https://login.wrike.com/oauth2/authorize/v4",
    token_url="https://login.wrike.com/oauth2/token",
    client_id_setting="WRIKE_CLIENT_ID",
    client_secret_setting="WRIKE_CLIENT_SECRET",
    scopes=["wsReadWrite"],
    userinfo_url="https://www.wrike.com/api/v4/contacts?me=true",
)

# ── Eventbrite ────────────────────────────────────────────────────────────────
EVENTBRITE_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="eventbrite",
    authorize_url="https://www.eventbrite.com/oauth/authorize",
    token_url="https://www.eventbrite.com/oauth/token",
    client_id_setting="EVENTBRITE_CLIENT_ID",
    client_secret_setting="EVENTBRITE_CLIENT_SECRET",
    scopes=[],
    userinfo_url="https://www.eventbriteapi.com/v3/users/me/",
)

# ── Basecamp ──────────────────────────────────────────────────────────────────
BASECAMP_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="basecamp",
    authorize_url="https://launchpad.37signals.com/authorization/new",
    token_url="https://launchpad.37signals.com/authorization/token",
    client_id_setting="BASECAMP_CLIENT_ID",
    client_secret_setting="BASECAMP_CLIENT_SECRET",
    scopes=[],
    extra_authorize_params={"type": "web_server"},
    userinfo_url="https://launchpad.37signals.com/authorization.json",
)

WRIKE_OAUTH_FLOW = GenericOAuth2Flow(WRIKE_OAUTH_CONFIG)
EVENTBRITE_OAUTH_FLOW = GenericOAuth2Flow(EVENTBRITE_OAUTH_CONFIG)
BASECAMP_OAUTH_FLOW = GenericOAuth2Flow(BASECAMP_OAUTH_CONFIG)

# ── QuickBooks ────────────────────────────────────────────────────────────────
QUICKBOOKS_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="quickbooks",
    authorize_url="https://appcenter.intuit.com/connect/oauth2",
    token_url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
    client_id_setting="QUICKBOOKS_CLIENT_ID",
    client_secret_setting="QUICKBOOKS_CLIENT_SECRET",
    scopes=["com.intuit.quickbooks.accounting"],
)

# ── Xero ──────────────────────────────────────────────────────────────────────
XERO_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="xero",
    authorize_url="https://login.xero.com/identity/connect/authorize",
    token_url="https://identity.xero.com/connect/token",
    client_id_setting="XERO_CLIENT_ID",
    client_secret_setting="XERO_CLIENT_SECRET",
    scopes=["openid", "profile", "email", "accounting.transactions", "accounting.contacts", "accounting.settings", "offline_access"],
)

QUICKBOOKS_OAUTH_FLOW = GenericOAuth2Flow(QUICKBOOKS_OAUTH_CONFIG)
XERO_OAUTH_FLOW = GenericOAuth2Flow(XERO_OAUTH_CONFIG)

# ── WordPress ─────────────────────────────────────────────────────────────────
WORDPRESS_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="wordpress",
    authorize_url="https://public-api.wordpress.com/oauth2/authorize",
    token_url="https://public-api.wordpress.com/oauth2/token",
    client_id_setting="WORDPRESS_CLIENT_ID",
    client_secret_setting="WORDPRESS_CLIENT_SECRET",
    scopes=["global"],
    userinfo_url="https://public-api.wordpress.com/rest/v1.1/me",
)

# ── Square ────────────────────────────────────────────────────────────────────
SQUARE_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="square",
    authorize_url="https://connect.squareup.com/oauth2/authorize",
    token_url="https://connect.squareup.com/oauth2/token",
    client_id_setting="SQUARE_CLIENT_ID",
    client_secret_setting="SQUARE_CLIENT_SECRET",
    scopes=["PAYMENTS_READ", "PAYMENTS_WRITE", "CUSTOMERS_READ", "CUSTOMERS_WRITE", "ORDERS_READ", "ORDERS_WRITE", "ITEMS_READ", "INVOICES_READ", "INVOICES_WRITE"],
)

WORDPRESS_OAUTH_FLOW = GenericOAuth2Flow(WORDPRESS_OAUTH_CONFIG)
SQUARE_OAUTH_FLOW = GenericOAuth2Flow(SQUARE_OAUTH_CONFIG)

# ── Microsoft Outlook ───────────────────────────────────────────────────��─────
OUTLOOK_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="outlook",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    client_id_setting="MICROSOFT_CLIENT_ID",
    client_secret_setting="MICROSOFT_CLIENT_SECRET",
    scopes=["openid", "profile", "email", "offline_access",
            "Mail.Read", "Mail.Send", "Mail.ReadWrite",
            "Calendars.Read", "Calendars.ReadWrite",
            "Contacts.Read", "Contacts.ReadWrite"],
    userinfo_url="https://graph.microsoft.com/v1.0/me",
)

# ── Microsoft Teams ───────────────────────────────────────────────────────────
MICROSOFT_TEAMS_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="microsoft_teams",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    client_id_setting="MICROSOFT_CLIENT_ID",
    client_secret_setting="MICROSOFT_CLIENT_SECRET",
    scopes=["openid", "profile", "email", "offline_access",
            "Team.ReadBasic.All", "Channel.ReadBasic.All",
            "ChannelMessage.Read.All", "ChannelMessage.Send",
            "Chat.Read", "Chat.ReadWrite", "ChatMessage.Send"],
    userinfo_url="https://graph.microsoft.com/v1.0/me",
)

# ── OneDrive ──────────────────────────────────────────────────────────────────
ONEDRIVE_OAUTH_CONFIG = GenericOAuth2Config(
    provider_name="onedrive",
    authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    client_id_setting="MICROSOFT_CLIENT_ID",
    client_secret_setting="MICROSOFT_CLIENT_SECRET",
    scopes=["openid", "profile", "email", "offline_access",
            "Files.Read.All", "Files.ReadWrite.All"],
    userinfo_url="https://graph.microsoft.com/v1.0/me",
)

OUTLOOK_OAUTH_FLOW = GenericOAuth2Flow(OUTLOOK_OAUTH_CONFIG)
MICROSOFT_TEAMS_OAUTH_FLOW = GenericOAuth2Flow(MICROSOFT_TEAMS_OAUTH_CONFIG)
ONEDRIVE_OAUTH_FLOW = GenericOAuth2Flow(ONEDRIVE_OAUTH_CONFIG)
