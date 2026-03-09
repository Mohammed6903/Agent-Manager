"""Google Docs operations service."""

from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict

from .gmail_auth_service import get_valid_credentials
from ..integrations.sdk_logger import log_integration_call

def get_service(db: Session, agent_id: str):
    creds = get_valid_credentials(db, agent_id)
    if not creds:
        return None
    return build("docs", "v1", credentials=creds)

@log_integration_call("google_docs", "POST", "/documents")
def create_document(db: Session, agent_id: str, title: str):
    """Create a new Google Doc."""
    service = get_service(db, agent_id)
    if not service:
        return None

    body = {"title": title}
    # Cast to Any to allow adding custom 'documentUrl' and bypass TypedDict restrictions
    doc: Any = service.documents().create(body=body).execute()
    
    doc_id = doc.get("documentId")
    doc["documentUrl"] = f"https://docs.google.com/document/d/{doc_id}/edit"
    return doc

@log_integration_call("google_docs", "GET", "/documents/{documentId}")
def get_document(db: Session, agent_id: str, document_id: str):
    """Fetch the full document content and metadata."""
    service = get_service(db, agent_id)
    if not service:
        return None

    return service.documents().get(documentId=document_id).execute()

@log_integration_call("google_docs", "POST", "/documents/{documentId}:batchUpdate")
def insert_text(db: Session, agent_id: str, document_id: str, text: str, index: int = 1):
    """Insert text at a specific index."""
    service = get_service(db, agent_id)
    if not service:
        return None

    requests = [
        {
            "insertText": {
                "location": {"index": index},
                "text": text
            }
        }
    ]
    return service.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()

@log_integration_call("google_docs", "POST", "/documents/{documentId}:batchUpdate")
def append_text(db: Session, agent_id: str, document_id: str, text: str):
    """Helper to append text to the end of the document."""
    doc = get_document(db, agent_id, document_id)
    if not doc:
        return None
    
    # Safe navigation through the document structure
    # Google Docs structure: doc -> body -> content (list of structural elements)
    body: Dict[str, Any] = doc.get("body", {})
    content: List[Dict[str, Any]] = body.get("content", [])
    
    if content:
        # The last element in a doc usually has an endIndex representing the end of the file.
        # We subtract 1 to stay before the final mandatory newline.
        last_element = content[-1]
        end_index = last_element.get("endIndex", 1)
        # Docs must have a newline at the very end (index 0 is start, endIndex is after last char)
        target_index = max(1, end_index - 1)
    else:
        target_index = 1

    return insert_text(db, agent_id, document_id, text, target_index)

@log_integration_call("google_docs", "POST", "/documents/{documentId}:batchUpdate")
def batch_update(db: Session, agent_id: str, document_id: str, requests: List[dict]):
    """Execute multiple formatting or editing requests."""
    service = get_service(db, agent_id)
    if not service:
        return None

    return service.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()