"""Gmail email operations service."""

from googleapiclient.discovery import build
from .gmail_auth_service import get_valid_credentials
from sqlalchemy.orm import Session
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any


def get_service(db: Session, agent_id: str):
    creds = get_valid_credentials(db, agent_id)
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_header(headers: list, name: str):
    """Extract a header value by name (case-insensitive)."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return None


def _extract_body(payload: dict):
    """Recursively extract plain text and HTML body from a message payload."""
    text_body = ""
    html_body = ""

    def _walk(part):
        nonlocal text_body, html_body
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")

        if data and mime == "text/plain":
            text_body += base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        elif data and mime == "text/html":
            html_body += base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)
    return text_body, html_body


def _extract_attachments(payload: dict):
    """Extract attachment metadata from a message payload."""
    attachments = []
    def _walk(part):
        filename = part.get("filename")
        body = part.get("body", {})
        if filename and body.get("attachmentId"):
            attachments.append({
                "filename": filename,
                "mimeType": part.get("mimeType"),
                "size": body.get("size", 0),
                "attachmentId": body["attachmentId"],
            })
        for sub in part.get("parts", []):
            _walk(sub)
    _walk(payload)
    return attachments


def _parse_message(message: dict):
    """Parse a raw Gmail API message into a rich, agent-friendly dict."""
    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    text_body, html_body = _extract_body(payload)
    attachments = _extract_attachments(payload)

    return {
        "id": message["id"],
        "threadId": message.get("threadId"),
        "labelIds": message.get("labelIds", []),
        "subject": _get_header(headers, "Subject"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "cc": _get_header(headers, "Cc"),
        "date": _get_header(headers, "Date"),
        "snippet": message.get("snippet", ""),
        "body": text_body or html_body,
        "body_html": html_body if html_body else None,
        "attachments": attachments,
    }


def _parse_message_summary(message: dict):
    """Parse a message into a lightweight summary (for list/search results)."""
    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    return {
        "id": message["id"],
        "threadId": message.get("threadId"),
        "labelIds": message.get("labelIds", []),
        "subject": _get_header(headers, "Subject"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "date": _get_header(headers, "Date"),
        "snippet": message.get("snippet", ""),
    }


# ── Core functions ───────────────────────────────────────────────────────────

def list_messages(
    db: Session,
    agent_id: str,
    max_results: int = 10,
    query: Optional[str] = None,
    label_ids: Optional[List[str]] = None,
):
    """List messages with optional Gmail search query and label filter.

    Returns enriched summaries (subject, from, to, date, snippet) so the
    agent can decide which messages to read in full without extra calls.
    """
    service = get_service(db, agent_id)
    if not service:
        return None

    kwargs = {"userId": "me", "maxResults": max_results}
    if query:
        kwargs["q"] = query
    if label_ids:
        kwargs["labelIds"] = label_ids

    response = service.users().messages().list(**kwargs).execute()
    message_ids = response.get("messages", [])

    if not message_ids:
        return []

    results = []
    for msg_ref in message_ids:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_ref["id"], format="full")
            .execute()
        )
        results.append(_parse_message_summary(msg))

    return results


def search_messages(
    db: Session,
    agent_id: str,
    query: str,
    max_results: int = 10,
):
    """Search messages using Gmail query syntax. Convenience wrapper."""
    return list_messages(db, agent_id, max_results=max_results, query=query)


def get_message(db: Session, agent_id: str, message_id: str):
    """Get full message with complete body, headers, labels, and attachments."""
    service = get_service(db, agent_id)
    if not service:
        return None

    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    return _parse_message(msg)


def batch_get_messages(db: Session, agent_id: str, message_ids: List[str]):
    """Get multiple messages by ID in one logical call."""
    service = get_service(db, agent_id)
    if not service:
        return None

    results = []
    for mid in message_ids:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=mid, format="full")
                .execute()
            )
            results.append(_parse_message(msg))
        except Exception:
            results.append({"id": mid, "error": "Failed to fetch message"})
    return results


def get_thread(db: Session, agent_id: str, thread_id: str):
    """Get all messages in a thread, each with full metadata."""
    service = get_service(db, agent_id)
    if not service:
        return None

    thread = (
        service.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )

    messages = thread.get("messages", [])
    return {
        "threadId": thread_id,
        "messages": [_parse_message(m) for m in messages],
        "message_count": len(messages),
    }


def send_message(
    db: Session,
    agent_id: str,
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html_body: Optional[str] = None,
):
    """Send an email with optional cc, bcc, and HTML body."""
    service = get_service(db, agent_id)
    if not service:
        return None

    if html_body:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(body, "plain"))
        message.attach(MIMEText(html_body, "html"))
    else:
        message = MIMEText(body)

    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return result


def reply_to_message(
    db: Session,
    agent_id: str,
    message_id: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html_body: Optional[str] = None,
):
    """Reply to a message in its thread with proper headers."""
    service = get_service(db, agent_id)
    if not service:
        return None

    # Get original message to extract thread info and headers
    original = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    headers = original.get("payload", {}).get("headers", [])
    thread_id = original.get("threadId")
    original_subject = _get_header(headers, "Subject") or ""
    original_from = _get_header(headers, "From") or ""
    original_message_id = _get_header(headers, "Message-ID") or ""
    references = _get_header(headers, "References") or ""

    if html_body:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(body, "plain"))
        message.attach(MIMEText(html_body, "html"))
    else:
        message = MIMEText(body)

    # Set reply headers
    reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
    message["to"] = original_from
    message["subject"] = reply_subject
    message["In-Reply-To"] = original_message_id
    message["References"] = f"{references} {original_message_id}".strip()
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": thread_id})
        .execute()
    )
    return result


def modify_labels(
    db: Session,
    agent_id: str,
    message_ids: List[str],
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
):
    """Add/remove labels on one or more messages.

    Common patterns for agents:
      - Archive:     remove_labels=["INBOX"]
      - Mark read:   remove_labels=["UNREAD"]
      - Mark unread: add_labels=["UNREAD"]
      - Star:        add_labels=["STARRED"]
      - Trash:       add_labels=["TRASH"]
    """
    service = get_service(db, agent_id)
    if not service:
        return None

    body_payload: Dict[str, Any] = {}
    if add_labels:
        body_payload["addLabelIds"] = add_labels
    if remove_labels:
        body_payload["removeLabelIds"] = remove_labels

    results = []
    for mid in message_ids:
        result = (
            service.users()
            .messages()
            .modify(userId="me", id=mid, body=body_payload)
            .execute()
        )
        results.append({"id": result["id"], "labelIds": result.get("labelIds", [])})

    return {"modified": results}


def get_attachment(db: Session, agent_id: str, message_id: str, attachment_id: str):
    """Download an attachment by ID and return its base64 data."""
    service = get_service(db, agent_id)
    if not service:
        return None

    attachment = (
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    return {
        "data": attachment.get("data"),
        "size": attachment.get("size"),
    }
