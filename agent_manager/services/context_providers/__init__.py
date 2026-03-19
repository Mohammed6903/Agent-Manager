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

PROVIDERS: dict[str, IntegrationContextProvider] = {
    "gmail": GmailContextProvider(),
    "google_calendar": CalendarContextProvider(),
    "google_docs": DocsContextProvider(),
    "google_sheets": SheetsContextProvider(),
}


def get_provider(integration_name: str) -> IntegrationContextProvider | None:
    """Look up a registered provider by integration name."""
    return PROVIDERS.get(integration_name)
