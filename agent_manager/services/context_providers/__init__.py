"""Integration context provider registry.

Each third-party integration that supports context ingestion implements
``IntegrationContextProvider`` and is registered in ``PROVIDERS``.

Adding a new integration:
    1. Create a class implementing IntegrationContextProvider.
    2. Add an entry to PROVIDERS below.
    3. That's it — the service layer, router, injection, and Celery tasks
       all resolve behaviour through this registry.
"""
from __future__ import annotations

from .base import IntegrationContextProvider
from .gmail_provider import GmailContextProvider
from .calendar_provider import CalendarContextProvider
from .docs_provider import DocsContextProvider
from .sheets_provider import SheetsContextProvider
from .drive_provider import DriveContextProvider

PROVIDERS: dict[str, IntegrationContextProvider] = {
    "gmail": GmailContextProvider(),
    "google_calendar": CalendarContextProvider(),
    "google_docs": DocsContextProvider(),
    "google_sheets": SheetsContextProvider(),
    "google_drive": DriveContextProvider(),
}


def get_provider(integration_name: str) -> IntegrationContextProvider | None:
    """Look up a registered provider by integration name.

    Returns None if the provider doesn't exist OR if the underlying
    integration is inactive (is_active=False on the integration class).
    """
    from agent_manager.integrations import is_integration_active
    provider = PROVIDERS.get(integration_name)
    if provider is None:
        return None
    if not is_integration_active(integration_name):
        return None
    return provider


def list_active_providers() -> list[IntegrationContextProvider]:
    """Return only providers whose underlying integration is active."""
    from agent_manager.integrations import is_integration_active
    return [p for name, p in PROVIDERS.items() if is_integration_active(name)]
