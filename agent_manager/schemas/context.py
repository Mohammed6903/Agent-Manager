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


class UploadPdfResponse(BaseModel):
    """Response for POST /contexts/upload-pdf.

    Wraps the freshly-created GlobalContext with extraction metadata so the
    client can surface page counts, the OCR mode that was used, and — most
    importantly — a ``warning`` string when our heuristics detected that
    the PDF is probably scanned or image-based and would benefit from
    re-uploading with OCR enabled.
    """

    context: GlobalContextResponse
    page_count: int = Field(..., description="Total number of pages in the PDF")
    char_count: int = Field(
        ..., description="Characters of markdown text produced by the extraction"
    )
    used_ocr: bool = Field(
        ..., description="Whether Mistral OCR was used. False means local text extraction."
    )
    warning: Optional[str] = Field(
        None,
        description=(
            "Professional warning message when the extraction heuristic "
            "detected that the document may be scanned or image-based and "
            "the text density is lower than expected. None when the "
            "extraction result looks complete or when OCR was used."
        ),
    )
