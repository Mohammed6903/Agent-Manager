"""Pydantic request models for Gmail, Calendar, and Secrets endpoints."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel


# ── Auth ────────────────────────────────────────────────────────────────────────


class ManualCallbackRequest(BaseModel):
    agent_id: str
    code: Optional[str] = None
    redirect_url: Optional[str] = None


# ── Email ───────────────────────────────────────────────────────────────────────


class SendEmailRequest(BaseModel):
    agent_id: str
    to: str
    subject: str
    body: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
    html_body: Optional[str] = None


class ReplyRequest(BaseModel):
    agent_id: str
    message_id: str
    body: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
    html_body: Optional[str] = None


class ModifyLabelsRequest(BaseModel):
    agent_id: str
    message_ids: List[str]
    add_labels: Optional[List[str]] = None
    remove_labels: Optional[List[str]] = None


class BatchReadRequest(BaseModel):
    agent_id: str
    message_ids: List[str]


# ── Calendar ────────────────────────────────────────────────────────────────────


class CreateEventRequest(BaseModel):
    agent_id: str
    summary: str
    start_time: str  # ISO format: 2024-01-15T10:00:00
    end_time: str
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    timezone: str = "UTC"           # IANA timezone, e.g. "America/New_York"
    add_meet: bool = False           # Generate a Google Meet link


class UpdateEventRequest(BaseModel):
    agent_id: str
    summary: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None


# ── Drive ───────────────────────────────────────────────────────────────────────


class MoveFileRequest(BaseModel):
    agent_id: str
    new_parent_id: str


class RenameFileRequest(BaseModel):
    agent_id: str
    new_name: str


class ShareFileRequest(BaseModel):
    agent_id: str
    email: str
    role: str = "reader"  # reader | commenter | writer


class CreateFolderRequest(BaseModel):
    agent_id: str
    name: str
    parent_id: Optional[str] = None


# ── Sheets ───────────────────────────────────────────────────────────────────────


class CreateSpreadsheetRequest(BaseModel):
    agent_id: str
    title: str


class WriteRangeRequest(BaseModel):
    agent_id: str
    range: str
    values: List[List[Any]]
    value_input_option: str = "USER_ENTERED"  # RAW | USER_ENTERED


class AppendRowsRequest(BaseModel):
    agent_id: str
    range: str
    values: List[List[Any]]
    value_input_option: str = "USER_ENTERED"


class AddSheetRequest(BaseModel):
    agent_id: str
    sheet_title: str

# ── Google Docs ─────────────────────────────────────────────────────────────────


class CreateDocumentRequest(BaseModel):
    agent_id: str
    title: str

class AppendTextRequest(BaseModel):
    agent_id: str
    text: str

class InsertTextRequest(BaseModel):
    agent_id: str
    text: str
    index: int = 1  # 1 is after the dummy newline in a new doc

class BatchUpdateRequest(BaseModel):
    agent_id: str
    requests: List[dict]

# ── Google Meet ─────────────────────────────────────────────────────────────────

class CreateMeetSpaceRequest(BaseModel):
    agent_id: str
    config: Optional[Dict[str, Any]] = None  # e.g., entry_point_access_video_only

class UpdateMeetSpaceRequest(BaseModel):
    agent_id: str
    config: Dict[str, Any]

# ── Secrets ─────────────────────────────────────────────────────────────────────


class SecretUpsertRequest(BaseModel):
    agent_id: str
    service_name: str
    secret_data: Dict[str, Any]
