from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class GlobalContextCreate(BaseModel):
    name: str = Field(..., description="Unique name for the context")
    content: str = Field(..., description="The knowledge content")
    org_id: Optional[str] = None

class GlobalContextResponse(BaseModel):
    id: UUID
    name: str
    content: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class GlobalContextUpdate(BaseModel):
    name: Optional[str] = Field(None, description="New name for the context")
    content: Optional[str] = Field(None, description="New content for the context")

class AgentContextAssignRequest(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent")
    context_id: str = Field(..., description="The ID of the context to assign")

class AgentContextResponse(BaseModel):
    id: UUID
    agent_id: str
    context_id: UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ContextNameListResponse(BaseModel):
    contexts: List[str]

class ContextListResponse(BaseModel):
    contexts: List[GlobalContextResponse]

class ContextContentResponse(BaseModel):
    id: UUID
    name: str
    content: str


class UploadDocumentResponse(BaseModel):
    """Response for POST /contexts/upload-document.

    Wraps the freshly-created GlobalContext with extraction metadata so
    the client can surface page counts, the extraction mode used, and —
    most importantly — a ``warning`` string when our heuristics detected
    that a PDF is probably scanned or image-based and would benefit
    from re-uploading with OCR enabled. DOCX uploads never emit a
    warning because DOCX is always XML-based with readable text.
    """

    context: GlobalContextResponse
    source_format: str = Field(
        ...,
        description="File format the upload was classified as. 'pdf' or 'docx'.",
    )
    page_count: int = Field(
        ...,
        description=(
            "Number of pages in the source document. For DOCX this is "
            "always 1 because DOCX doesn't have a meaningful page count "
            "for content extraction — pagination is a display concept."
        ),
    )
    char_count: int = Field(
        ..., description="Characters of markdown text produced by the extraction."
    )
    used_ocr: bool = Field(
        ...,
        description=(
            "Whether Mistral OCR was used. False means local text "
            "extraction (pdfplumber for PDF, python-docx for DOCX). "
            "Always False for DOCX."
        ),
    )
    warning: Optional[str] = Field(
        None,
        description=(
            "Professional warning message when the PDF extraction "
            "heuristic detected that the document may be scanned or "
            "image-based and the text density is lower than expected. "
            "None for DOCX uploads, for OCR uploads, and for PDF "
            "uploads where the result looks complete."
        ),
    )


# Backwards-compat alias — keep the old name importable for any scripts
# or future tests that still reference it.
UploadPdfResponse = UploadDocumentResponse
