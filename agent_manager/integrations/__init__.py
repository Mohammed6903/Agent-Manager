from typing import Dict, Type, List

from .base import BaseIntegration, AuthFlowType
# from .notion import NotionIntegration  # temporarily hidden
from .google import GmailIntegration, GoogleCalendarIntegration, GoogleDriveIntegration, GoogleSheetsIntegration, GoogleDocsIntegration, GoogleMeetIntegration

# Registry of all available integrations
INTEGRATION_REGISTRY: Dict[str, Type[BaseIntegration]] = {
    # NotionIntegration.name: NotionIntegration,  # temporarily hidden
    GmailIntegration.name: GmailIntegration,
    GoogleCalendarIntegration.name: GoogleCalendarIntegration,
    GoogleDriveIntegration.name: GoogleDriveIntegration,
    GoogleSheetsIntegration.name: GoogleSheetsIntegration,
    GoogleDocsIntegration.name: GoogleDocsIntegration,
    GoogleMeetIntegration.name: GoogleMeetIntegration,
}


def get_integration(name: str) -> Type[BaseIntegration]:
    """Retrieve an integration class by its internal name."""
    cls = INTEGRATION_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Integration '{name}' not found in registry.")
    return cls


def list_integrations() -> List[Type[BaseIntegration]]:
    """List all registered integration classes."""
    return list(INTEGRATION_REGISTRY.values())
