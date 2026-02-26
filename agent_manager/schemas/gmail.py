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


class UpdateEventRequest(BaseModel):
    agent_id: str
    summary: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None


# ── Secrets ─────────────────────────────────────────────────────────────────────


class SecretUpsertRequest(BaseModel):
    agent_id: str
    service_name: str
    secret_data: Dict[str, Any]
