"""Gmail purely email endpoints router."""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import gmail_service
from ..schemas.google import (
    SendEmailRequest,
    ReplyRequest,
    ModifyLabelsRequest,
    BatchReadRequest,
)

router = APIRouter()

@router.get("/list", tags=["Gmail Email"])
def list_emails(
    agent_id: str,
    max_results: int = 10,
    query: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List emails with optional Gmail search query.

    The `query` param supports full Gmail search syntax, e.g.:
    - `is:unread in:inbox`
    - `from:someone@example.com`
    - `subject:invoice newer_than:7d`
    - `category:primary is:unread`
    - `has:attachment`

    Returns enriched summaries (subject, from, to, date, snippet, labels).
    """
    try:
        result = gmail_service.list_messages(db, agent_id, max_results, query=query)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", tags=["Gmail Email"])
def search_emails(
    agent_id: str,
    query: str,
    max_results: int = 10,
    db: Session = Depends(get_db),
):
    """Search emails using Gmail query syntax.

    Examples:
    - `is:unread category:primary` — unread primary emails
    - `from:boss@company.com newer_than:3d` — recent emails from boss
    - `in:sent to:client@example.com` — sent emails to a client
    - `subject:meeting after:2026/02/01` — meetings since Feb 1
    """
    try:
        result = gmail_service.search_messages(db, agent_id, query, max_results)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/read", tags=["Gmail Email"])
def read_email(agent_id: str, message_id: str, db: Session = Depends(get_db)):
    """Read a full email — complete body (no truncation), all headers, labels,
    thread_id, and attachment metadata."""
    try:
        email_data = gmail_service.get_message(db, agent_id, message_id)
        if email_data is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return email_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch_read", tags=["Gmail Email"])
def batch_read_emails(body: BatchReadRequest, db: Session = Depends(get_db)):
    """Read multiple emails by ID in a single call."""
    try:
        results = gmail_service.batch_get_messages(db, body.agent_id, body.message_ids)
        if results is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"messages": results, "count": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thread", tags=["Gmail Email"])
def get_thread(agent_id: str, thread_id: str, db: Session = Depends(get_db)):
    """Get all messages in a conversation thread."""
    try:
        thread = gmail_service.get_thread(db, agent_id, thread_id)
        if thread is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return thread
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send", tags=["Gmail Email"])
def send_email(body: SendEmailRequest, db: Session = Depends(get_db)):
    """Send an email with optional cc, bcc, and HTML body."""
    try:
        result = gmail_service.send_message(
            db, body.agent_id, body.to, body.subject, body.body,
            cc=body.cc, bcc=body.bcc, html_body=body.html_body,
        )
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"status": "sent", "message_id": result["id"], "thread_id": result.get("threadId")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reply", tags=["Gmail Email"])
def reply_to_email(body: ReplyRequest, db: Session = Depends(get_db)):
    """Reply to an email in its thread with proper In-Reply-To/References headers."""
    try:
        result = gmail_service.reply_to_message(
            db, body.agent_id, body.message_id, body.body,
            cc=body.cc, bcc=body.bcc, html_body=body.html_body,
        )
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"status": "sent", "message_id": result["id"], "thread_id": result.get("threadId")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/modify", tags=["Gmail Email"])
def modify_email_labels(body: ModifyLabelsRequest, db: Session = Depends(get_db)):
    """Add/remove labels on messages.

    Common patterns:
    - Archive:     remove_labels=["INBOX"]
    - Mark read:   remove_labels=["UNREAD"]
    - Mark unread: add_labels=["UNREAD"]
    - Star:        add_labels=["STARRED"]
    - Trash:       add_labels=["TRASH"]
    """
    try:
        result = gmail_service.modify_labels(
            db, body.agent_id, body.message_ids,
            add_labels=body.add_labels, remove_labels=body.remove_labels,
        )
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attachment", tags=["Gmail Email"])
def get_attachment(
    agent_id: str,
    message_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
):
    """Download an attachment by its attachment_id (returned in email read results)."""
    try:
        result = gmail_service.get_attachment(db, agent_id, message_id, attachment_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
