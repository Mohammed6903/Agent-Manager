"""Google Docs endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import docs_service
from ..schemas.google import (
    CreateDocumentRequest,
    AppendTextRequest,
    InsertTextRequest,
    BatchUpdateRequest,
)

router = APIRouter()

@router.post("/documents", tags=["Google Docs"])
def create_document(body: CreateDocumentRequest, db: Session = Depends(get_db)):
    """Create a new document."""
    try:
        result = docs_service.create_document(db, body.agent_id, body.title)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents/{document_id}", tags=["Google Docs"])
def get_document(agent_id: str, document_id: str, db: Session = Depends(get_db)):
    """Get the full document structure."""
    try:
        result = docs_service.get_document(db, agent_id, document_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents/{document_id}/append", tags=["Google Docs"])
def append_text(document_id: str, body: AppendTextRequest, db: Session = Depends(get_db)):
    """Append text to the end of the document."""
    try:
        result = docs_service.append_text(db, body.agent_id, document_id, body.text)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents/{document_id}/batchUpdate", tags=["Google Docs"])
def batch_update(document_id: str, body: BatchUpdateRequest, db: Session = Depends(get_db)):
    """Apply multiple updates (formatting, insertions, deletions)."""
    try:
        result = docs_service.batch_update(db, body.agent_id, document_id, body.requests)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))