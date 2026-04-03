from typing import Dict, Type, List

from .base import BaseIntegration, AuthFlowType
from .notion.integration import NotionIntegration
from .google import (GmailIntegration, GoogleCalendarIntegration, GoogleDriveIntegration,
    GoogleSheetsIntegration, GoogleDocsIntegration, GoogleMeetIntegration,
    GoogleSlidesIntegration, GoogleFormsIntegration, GoogleAdsIntegration,
    YouTubeIntegration, GoogleAnalyticsIntegration, GoogleSearchConsoleIntegration)
from .twitter.twitter import TwitterIntegration
from .linkedin.linkedin import LinkedInIntegration
from .slack.integration import SlackIntegration
from .github.integration import GitHubIntegration
from .trello.integration import TrelloIntegration
from .airtable.integration import AirtableIntegration
from .asana.integration import AsanaIntegration
from .clickup.integration import ClickUpIntegration
from .todoist.integration import TodoistIntegration
from .typeform.integration import TypeformIntegration
from .stripe.integration import StripeIntegration
from .hubspot.integration import HubSpotIntegration
from .jira.integration import JiraIntegration
from .salesforce.integration import SalesforceIntegration
from .monday.integration import MondayIntegration
from .dropbox.integration import DropboxIntegration
from .mailchimp.integration import MailchimpIntegration
from .calendly.integration import CalendlyIntegration
from .pipedrive.integration import PipedriveIntegration
from .confluence.integration import ConfluenceIntegration
from .zohocrm.integration import ZohoCRMIntegration
from .linear.integration import LinearIntegration
from .box.integration import BoxIntegration
from .buffer.integration import BufferIntegration
from .resend.integration import ResendIntegration
from .sendgrid.integration import SendGridIntegration
from .wrike.integration import WrikeIntegration
from .eventbrite.integration import EventbriteIntegration
from .basecamp.integration import BasecampIntegration
from .chargebee.integration import ChargebeeIntegration
from .clockify.integration import ClockifyIntegration
from .quickbooks.integration import QuickBooksIntegration
from .xero.integration import XeroIntegration
from .twilio.integration import TwilioIntegration
from .whatsapp.integration import WhatsAppBusinessIntegration
from .telegram.integration import TelegramBotIntegration
from .wordpress.integration import WordPressIntegration
from .woocommerce.integration import WooCommerceIntegration
from .square.integration import SquareIntegration
from .sentry.integration import SentryIntegration
from .posthog.integration import PostHogIntegration
from .outlook.integration import OutlookIntegration
from .microsoft_teams.integration import MicrosoftTeamsIntegration
from .onedrive.integration import OneDriveIntegration

# Registry of all available integrations
INTEGRATION_REGISTRY: Dict[str, Type[BaseIntegration]] = {
    NotionIntegration.name: NotionIntegration,
    GmailIntegration.name: GmailIntegration,
    GoogleCalendarIntegration.name: GoogleCalendarIntegration,
    GoogleDriveIntegration.name: GoogleDriveIntegration,
    GoogleSheetsIntegration.name: GoogleSheetsIntegration,
    GoogleDocsIntegration.name: GoogleDocsIntegration,
    GoogleMeetIntegration.name: GoogleMeetIntegration,
    GoogleSlidesIntegration.name: GoogleSlidesIntegration,
    GoogleFormsIntegration.name: GoogleFormsIntegration,
    GoogleAdsIntegration.name: GoogleAdsIntegration,
    YouTubeIntegration.name: YouTubeIntegration,
    GoogleAnalyticsIntegration.name: GoogleAnalyticsIntegration,
    GoogleSearchConsoleIntegration.name: GoogleSearchConsoleIntegration,
    TwitterIntegration.name: TwitterIntegration,
    LinkedInIntegration.name: LinkedInIntegration,
    SlackIntegration.name: SlackIntegration,
    GitHubIntegration.name: GitHubIntegration,
    TrelloIntegration.name: TrelloIntegration,
    AirtableIntegration.name: AirtableIntegration,
    AsanaIntegration.name: AsanaIntegration,
    ClickUpIntegration.name: ClickUpIntegration,
    TodoistIntegration.name: TodoistIntegration,
    TypeformIntegration.name: TypeformIntegration,
    StripeIntegration.name: StripeIntegration,
    HubSpotIntegration.name: HubSpotIntegration,
    JiraIntegration.name: JiraIntegration,
    SalesforceIntegration.name: SalesforceIntegration,
    MondayIntegration.name: MondayIntegration,
    DropboxIntegration.name: DropboxIntegration,
    MailchimpIntegration.name: MailchimpIntegration,
    CalendlyIntegration.name: CalendlyIntegration,
    PipedriveIntegration.name: PipedriveIntegration,
    ConfluenceIntegration.name: ConfluenceIntegration,
    ZohoCRMIntegration.name: ZohoCRMIntegration,
    LinearIntegration.name: LinearIntegration,
    BoxIntegration.name: BoxIntegration,
    BufferIntegration.name: BufferIntegration,
    ResendIntegration.name: ResendIntegration,
    SendGridIntegration.name: SendGridIntegration,
    WrikeIntegration.name: WrikeIntegration,
    EventbriteIntegration.name: EventbriteIntegration,
    BasecampIntegration.name: BasecampIntegration,
    ChargebeeIntegration.name: ChargebeeIntegration,
    ClockifyIntegration.name: ClockifyIntegration,
    QuickBooksIntegration.name: QuickBooksIntegration,
    XeroIntegration.name: XeroIntegration,
    TwilioIntegration.name: TwilioIntegration,
    WhatsAppBusinessIntegration.name: WhatsAppBusinessIntegration,
    TelegramBotIntegration.name: TelegramBotIntegration,
    WordPressIntegration.name: WordPressIntegration,
    WooCommerceIntegration.name: WooCommerceIntegration,
    SquareIntegration.name: SquareIntegration,
    SentryIntegration.name: SentryIntegration,
    PostHogIntegration.name: PostHogIntegration,
    OutlookIntegration.name: OutlookIntegration,
    MicrosoftTeamsIntegration.name: MicrosoftTeamsIntegration,
    OneDriveIntegration.name: OneDriveIntegration,
}


def get_integration(name: str, *, allow_inactive: bool = False) -> Type[BaseIntegration]:
    """Retrieve an integration class by its internal name.

    Raises ValueError when the integration does not exist or is inactive
    (unless *allow_inactive* is True — only needed for internal operations
    like credential cleanup on unassign).
    """
    cls = INTEGRATION_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Integration '{name}' not found in registry.")
    if not allow_inactive and not cls.is_active:
        raise ValueError(f"Integration '{name}' is currently inactive.")
    return cls


def list_integrations(*, include_inactive: bool = False) -> List[Type[BaseIntegration]]:
    """List registered integration classes.

    By default only active integrations are returned. Pass
    *include_inactive=True* to get everything (admin dashboards, etc.).
    """
    if include_inactive:
        return list(INTEGRATION_REGISTRY.values())
    return [cls for cls in INTEGRATION_REGISTRY.values() if cls.is_active]


def is_integration_active(name: str) -> bool:
    """Check whether an integration is registered and active."""
    cls = INTEGRATION_REGISTRY.get(name)
    return cls is not None and cls.is_active
