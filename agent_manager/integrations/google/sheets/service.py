"""Google Sheets operations service."""

from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from typing import Any, List

from agent_manager.integrations.google.gmail.auth_service import get_valid_credentials
from agent_manager.integrations.sdk_logger import log_integration_call


def get_service(db: Session, agent_id: str):
    creds = get_valid_credentials(db, agent_id)
    if not creds:
        return None
    return build("sheets", "v4", credentials=creds)


@log_integration_call("google_sheets", "POST", "/spreadsheets")
def create_spreadsheet(db: Session, agent_id: str, title: str):
    """Create a new empty spreadsheet."""
    service = get_service(db, agent_id)
    if not service:
        return None

    body = {"properties": {"title": title}}
    result = service.spreadsheets().create(body=body, fields="spreadsheetId,properties").execute()
    # spreadsheetUrl is not in the fields mask but we can construct it
    result["spreadsheetUrl"] = f"https://docs.google.com/spreadsheets/d/{result['spreadsheetId']}"
    return result


@log_integration_call("google_sheets", "GET", "/spreadsheets/{spreadsheetId}")
def get_spreadsheet(db: Session, agent_id: str, spreadsheet_id: str):
    """Get spreadsheet metadata including sheet names and properties."""
    service = get_service(db, agent_id)
    if not service:
        return None

    result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return {
        "spreadsheet_id": result["spreadsheetId"],
        "title": result["properties"]["title"],
        "url": result.get("spreadsheetUrl"),
        "sheets": [
            {"title": s["properties"]["title"], "sheet_id": s["properties"]["sheetId"]}
            for s in result.get("sheets", [])
        ],
    }


@log_integration_call("google_sheets", "GET", "/spreadsheets/{spreadsheetId}/values/{range}")
def read_range(db: Session, agent_id: str, spreadsheet_id: str, range_notation: str):
    """
    Read values from a range. range_notation examples:
      'Sheet1'           — entire sheet
      'Sheet1!A1:D10'   — specific range
    """
    service = get_service(db, agent_id)
    if not service:
        return None

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_notation)
        .execute()
    )
    return result.get("values", [])


@log_integration_call("google_sheets", "PUT", "/spreadsheets/{spreadsheetId}/values/{range}")
def write_range(
    db: Session,
    agent_id: str,
    spreadsheet_id: str,
    range_notation: str,
    values: List[List[Any]],
    value_input_option: str = "USER_ENTERED",
):
    """
    Write values to a range, overwriting existing content.
    value_input_option: 'RAW' (treat as-is) or 'USER_ENTERED' (parse like a user typed it).
    """
    service = get_service(db, agent_id)
    if not service:
        return None

    body = {"values": values}
    result = (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueInputOption=value_input_option,
            body=body,
        )
        .execute()
    )
    return result


@log_integration_call("google_sheets", "POST", "/spreadsheets/{spreadsheetId}/values/{range}:append")
def append_rows(
    db: Session,
    agent_id: str,
    spreadsheet_id: str,
    range_notation: str,
    values: List[List[Any]],
    value_input_option: str = "USER_ENTERED",
):
    """Append rows after the last row with data in the detected range."""
    service = get_service(db, agent_id)
    if not service:
        return None

    body = {"values": values}
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueInputOption=value_input_option,
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
    )
    return result


@log_integration_call("google_sheets", "POST", "/spreadsheets/{spreadsheetId}:batchUpdate")
def add_sheet(db: Session, agent_id: str, spreadsheet_id: str, sheet_title: str):
    """Add a new sheet (tab) to an existing spreadsheet."""
    service = get_service(db, agent_id)
    if not service:
        return None

    body = {
        "requests": [
            {"addSheet": {"properties": {"title": sheet_title}}}
        ]
    }
    result = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
    new_sheet = result["replies"][0]["addSheet"]["properties"]
    return {"sheet_id": new_sheet["sheetId"], "title": new_sheet["title"]}


@log_integration_call("google_sheets", "POST", "/spreadsheets/{spreadsheetId}:batchUpdate")
def clear_range(db: Session, agent_id: str, spreadsheet_id: str, range_notation: str):
    """Clear all values in a range without deleting the cells."""
    service = get_service(db, agent_id)
    if not service:
        return None

    result = (
        service.spreadsheets()
        .values()
        .clear(spreadsheetId=spreadsheet_id, range=range_notation, body={})
        .execute()
    )
    return result
