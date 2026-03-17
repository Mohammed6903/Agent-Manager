"""Google Calendar operations service."""

import uuid

from googleapiclient.discovery import build
from agent_manager.integrations.google.gmail.auth_service import get_valid_credentials
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional


from agent_manager.integrations.sdk_logger import log_integration_call


def get_service(db: Session, agent_id: str):
    creds = get_valid_credentials(db, agent_id)
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds)


@log_integration_call("google_calendar", "GET", "/calendars/primary/events (list)")
def list_events(db: Session, agent_id: str, max_results: int = 10, time_min: Optional[str] = None):
    """List upcoming calendar events."""
    service = get_service(db, agent_id)
    if not service:
        return None

    if not time_min:
        time_min = datetime.utcnow().isoformat() + "Z"

    results = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = results.get("items", [])
    return [
        {
            "id": event["id"],
            "summary": event.get("summary", "No title"),
            "start": event["start"].get("dateTime", event["start"].get("date")),
            "end": event["end"].get("dateTime", event["end"].get("date")),
            "location": event.get("location"),
            "description": event.get("description"),
        }
        for event in events
    ]


@log_integration_call("google_calendar", "GET", "/calendars/primary/events/{eventId}")
def get_event(db: Session, agent_id: str, event_id: str):
    """Get a specific calendar event."""
    service = get_service(db, agent_id)
    if not service:
        return None

    event = service.events().get(calendarId="primary", eventId=event_id).execute()
    return {
        "id": event["id"],
        "summary": event.get("summary", "No title"),
        "start": event["start"].get("dateTime", event["start"].get("date")),
        "end": event["end"].get("dateTime", event["end"].get("date")),
        "location": event.get("location"),
        "description": event.get("description"),
        "attendees": event.get("attendees", []),
        "htmlLink": event.get("htmlLink"),
    }


@log_integration_call("google_calendar", "POST", "/calendars/primary/events")
def create_event(
    db: Session,
    agent_id: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[list] = None,
    timezone: str = "UTC",
    add_meet: bool = False,
):
    """Create a new calendar event with optional Google Meet and timezone support."""
    service = get_service(db, agent_id)
    if not service:
        return None

    event_body = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": timezone},
        "end": {"dateTime": end_time, "timeZone": timezone},
    }

    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendees:
        event_body["attendees"] = [{"email": email} for email in attendees]

    params = {}
    if add_meet:
        event_body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        params["conferenceDataVersion"] = 1

    event = service.events().insert(
        calendarId="primary",
        body=event_body,
        **params,
    ).execute()

    return {
        "id": event["id"],
        "summary": event.get("summary"),
        "htmlLink": event.get("htmlLink"),
        "meetLink": event.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri"),
    }


@log_integration_call("google_calendar", "PATCH", "/calendars/primary/events/{eventId}")
def update_event(
    db: Session,
    agent_id: str,
    event_id: str,
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
):
    """Update an existing calendar event."""
    service = get_service(db, agent_id)
    if not service:
        return None

    # Get existing event first
    event = service.events().get(calendarId="primary", eventId=event_id).execute()

    if summary:
        event["summary"] = summary
    if start_time:
        existing_tz = event.get("start", {}).get("timeZone", "UTC")
        event["start"] = {"dateTime": start_time, "timeZone": existing_tz}
    if end_time:
        existing_tz = event.get("end", {}).get("timeZone", "UTC")
        event["end"] = {"dateTime": end_time, "timeZone": existing_tz}
    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location

    updated_event = service.events().update(
        calendarId="primary", eventId=event_id, body=event
    ).execute()

    return {
        "id": updated_event["id"],
        "summary": updated_event.get("summary"),
        "htmlLink": updated_event.get("htmlLink"),
    }


@log_integration_call("google_calendar", "DELETE", "/calendars/primary/events/{eventId}")
def delete_event(db: Session, agent_id: str, event_id: str):
    """Delete a calendar event."""
    service = get_service(db, agent_id)
    if not service:
        return None

    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return {"status": "deleted", "event_id": event_id}
