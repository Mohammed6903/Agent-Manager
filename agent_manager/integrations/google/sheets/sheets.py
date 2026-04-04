from typing import List

from agent_manager.integrations.google.base_google import BaseGoogleIntegration
from agent_manager.integrations.base import EndpointDef, MetadataFieldDef, MetadataFieldType


class GoogleSheetsIntegration(BaseGoogleIntegration):
    """Integration definition for Google Sheets."""

    name = "google_sheets"
    display_name = "Google Sheets"
    test_connection = ("GET", "drive/v3/about?fields=user")
    base_url = "https://sheets.googleapis.com/v4"
    metadata_fields = [
        MetadataFieldDef(name="email", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="name", type=MetadataFieldType.STRING),
        MetadataFieldDef(name="picture", type=MetadataFieldType.IMAGE_URL),
    ]

    scopes: List[str] = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    endpoints: List[EndpointDef] = [
        EndpointDef(method="GET", path="/spreadsheets/{spreadsheetId}", description="Get spreadsheet metadata and sheet list"),
        EndpointDef(method="POST", path="/spreadsheets", description="Create a new spreadsheet"),
        EndpointDef(method="GET", path="/spreadsheets/{spreadsheetId}/values/{range}", description="Read cell values from a range"),
        EndpointDef(method="PUT", path="/spreadsheets/{spreadsheetId}/values/{range}", description="Write cell values to a range"),
        EndpointDef(method="POST", path="/spreadsheets/{spreadsheetId}/values/{range}:append", description="Append rows to a range"),
        EndpointDef(method="POST", path="/spreadsheets/{spreadsheetId}/values:batchGet", description="Read multiple ranges at once"),
        EndpointDef(method="POST", path="/spreadsheets/{spreadsheetId}/values:batchUpdate", description="Write to multiple ranges at once"),
        EndpointDef(method="POST", path="/spreadsheets/{spreadsheetId}:batchUpdate", description="Apply structural changes (add sheet, format cells, etc.)"),
    ]

    usage_instructions = (
        "Google authentication is handled out-of-band via user consent. "
        "Do not supply credentials directly. Use the provided OpenClaw Sheets tools to interact with this API natively."
    )
