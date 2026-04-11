import asyncio
import json
import os
import uuid
from typing import List, Optional

from celery.contrib.abortable import AbortableAsyncResult
from fastapi import APIRouter, Depends, File, HTTPException, Response, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..celery_app import celery_app
from ..config import settings
from ..database import get_db
from ..schemas.context import (
    AgentContextAssignRequest,
    AgentContextResponse,
    ContextContentResponse,
    ContextListResponse,
    GlobalContextCreate,
    GlobalContextResponse,
    GlobalContextUpdate,
    UploadDocumentResponse,
)
from ..services import manual_context_service, pdf_extraction_service
from ..services.context_service import ContextService
from ..services.third_party_context_service import ThirdPartyContextService
from agent_manager.tasks.gmail.ingest_task import get_active_tasks

router = APIRouter(tags=["Context Management"])

def get_context_service(db: Session = Depends(get_db)) -> ContextService:
    return ContextService(db)

# -- Global CRUD --


@router.post("", response_model=GlobalContextResponse)
def create_global_context(
    req: GlobalContextCreate,
    svc: ContextService = Depends(get_context_service),
    org_id: Optional[str] = Query(default=None),
):
    return svc.create_global_context(req, org_id=org_id)


# MIME types we accept for each format. UploadFile.content_type is
# whatever the client advertised, which can lie — so we also accept the
# extension as a fallback signal.
_PDF_MIMES = {"application/pdf", "application/x-pdf"}
_DOCX_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-docx",
    # Some browsers send the generic octet-stream on drag-and-drop, so
    # we also fall back to extension-based detection.
}


def _classify_upload(file: UploadFile) -> Optional[str]:
    """Classify an UploadFile as 'pdf' or 'docx', or None if unsupported.

    Uses content-type first (what the client said), then filename
    extension as a fallback (what the client *actually* uploaded).
    Returns the lowercase format string or None if we can't identify it.
    """
    content_type = (file.content_type or "").lower()
    ext = os.path.splitext(file.filename or "")[1].lower()

    if content_type in _PDF_MIMES or ext == ".pdf":
        return "pdf"
    if content_type in _DOCX_MIMES or ext == ".docx":
        return "docx"
    return None


@router.post("/upload-document", response_model=UploadDocumentResponse)
async def upload_document_context(
    file: UploadFile = File(
        ...,
        description="PDF or DOCX file to extract into a knowledge context",
    ),
    name: Optional[str] = Query(
        default=None,
        description=(
            "Optional context name. If omitted, derived from the uploaded "
            "filename (extension stripped). Must be unique within the org."
        ),
    ),
    use_ocr: bool = Query(
        default=False,
        description=(
            "For PDF uploads only: run Mistral OCR on the document. Enable "
            "for scanned, image-based, or heavily-formatted PDFs. Ignored "
            "for DOCX uploads since DOCX is always XML-based and readable."
        ),
    ),
    org_id: Optional[str] = Query(default=None),
    svc: ContextService = Depends(get_context_service),
):
    """Upload a PDF or DOCX and create a manual context from its contents.

    Flow:

    1. Classify the upload as PDF or DOCX by content-type + filename.
    2. Validate size (``MANUAL_CONTEXT_PDF_MAX_BYTES``) and non-empty.
    3. Extract markdown via ``pdf_extraction_service.extract_document``:
       - **PDF**: local pdfplumber path (fast, free) unless ``use_ocr=true``
         which routes to Mistral OCR (handles scans and complex layouts)
       - **DOCX**: python-docx path (XML-based, always direct text,
         no OCR option because DOCX cannot be image-only)
    4. Hand the extracted markdown to ``ContextService.create_global_context``,
       which triggers the existing chunk + embed + Qdrant RAG pipeline.
    5. Return the created context alongside extraction metadata
       (source_format, page count, char count, OCR flag, and — for PDFs —
       an optional warning that the document may need OCR for complete
       results).

    The response ``warning`` field is always ``null`` for DOCX uploads
    and for PDF uploads processed via OCR. It's only populated when the
    local PDF heuristic detects that the document is likely scanned
    and suggests the user re-upload with ``use_ocr=true``.
    """
    # ── Classify by content-type + extension ──────────────────────────
    source_format = _classify_upload(file)
    if source_format is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type. Expected a PDF or DOCX upload "
                f"(content-type 'application/pdf' or "
                f"'application/vnd.openxmlformats-officedocument."
                f"wordprocessingml.document', or a .pdf/.docx filename). "
                f"Got content-type={file.content_type!r}, "
                f"filename={file.filename!r}."
            ),
        )

    # ── Size guard ─────────────────────────────────────────────────────
    # Read the bytes up front (UploadFile is a SpooledTemporaryFile
    # under the hood so this is cheap for typical sizes). We reuse
    # MANUAL_CONTEXT_PDF_MAX_BYTES as the cap for both formats — the
    # name is historical; it's really "upload size limit" now.
    file_bytes = await file.read()
    size = len(file_bytes)
    if size > settings.MANUAL_CONTEXT_PDF_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Upload is {size:,} bytes, which exceeds the "
                f"{settings.MANUAL_CONTEXT_PDF_MAX_BYTES:,}-byte limit. "
                f"If you need to upload larger documents, raise "
                f"MANUAL_CONTEXT_PDF_MAX_BYTES in config."
            ),
        )
    if size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ── Extract ────────────────────────────────────────────────────────
    # InvalidDocumentError is a client error (bad file) → 400.
    # DocumentExtractionError covers downstream/provider failures → 502.
    try:
        result = await pdf_extraction_service.extract_document(
            file_bytes, source_format=source_format, use_ocr=use_ocr,
        )
    except pdf_extraction_service.InvalidDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except pdf_extraction_service.DocumentExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not result.markdown.strip():
        # PDF: happens when the local path returned nothing for a doc
        # that passed the front-door check (fully scanned, user didn't
        # opt into OCR). Tell them to retry with use_ocr=true.
        # DOCX: means the document had zero text content at all —
        # technically valid but semantically useless as a context.
        if source_format == "pdf":
            detail = (
                "No text content could be extracted from this PDF. It "
                "appears to be a scanned or image-only document. Retry "
                "with use_ocr=true to run Mistral OCR on the pages."
            )
        else:
            detail = (
                "The DOCX file contains no text content to index. "
                "Check that the document has text beyond images or "
                "embedded objects before re-uploading."
            )
        raise HTTPException(status_code=422, detail=detail)

    # ── Resolve the context name ───────────────────────────────────────
    final_name = (name or "").strip()
    if not final_name:
        base = os.path.basename(file.filename or f"uploaded-{source_format}")
        final_name = os.path.splitext(base)[0] or f"uploaded-{source_format}"

    # ── Create the context (runs the full RAG pipeline) ────────────────
    created = svc.create_global_context(
        GlobalContextCreate(name=final_name, content=result.markdown),
        org_id=org_id,
    )

    return UploadDocumentResponse(
        context=GlobalContextResponse.model_validate(created),
        source_format=result.source_format,
        page_count=result.page_count,
        char_count=result.char_count,
        used_ocr=result.used_ocr,
        warning=result.warning,
    )

@router.get("", response_model=List[GlobalContextResponse])
def list_global_contexts(
    svc: ContextService = Depends(get_context_service),
    org_id: Optional[str] = Query(default=None),
):
    return svc.list_global_contexts(org_id=org_id)

@router.get("/{context_id}", response_model=GlobalContextResponse)
def get_global_context(
    context_id: uuid.UUID,
    svc: ContextService = Depends(get_context_service),
):
    """Get a specific global context."""
    return svc.get_global_context_by_id(context_id)

@router.patch("/{context_id}", response_model=GlobalContextResponse)
def update_global_context(
    context_id: uuid.UUID,
    req: GlobalContextUpdate,
    svc: ContextService = Depends(get_context_service),
):
    """Update a specific global context."""
    return svc.update_global_context(context_id, req)
    
@router.delete("/{context_id}")
def delete_global_context(
    context_id: uuid.UUID,
    svc: ContextService = Depends(get_context_service),
):
    """Delete a specific global context."""
    svc.delete_global_context(context_id)
    return Response(status_code=204)


# -- Agent Assignment --

@router.post("/assign", response_model=AgentContextResponse)
def assign_context_to_agent(
    req: AgentContextAssignRequest,
    svc: ContextService = Depends(get_context_service),
):
    """Assign a global context to an agent."""
    return svc.assign_context(req)

@router.delete("/unassign/{agent_id}/{context_id}")
def unassign_context_from_agent(
    agent_id: str,
    context_id: uuid.UUID,
    svc: ContextService = Depends(get_context_service),
):
    """Unassign a global context from an agent."""
    svc.unassign_context(agent_id, context_id)
    return Response(status_code=204)


# -- Agent Contexts --

@router.get("/agent/{agent_id}", response_model=ContextListResponse)
def get_agent_contexts(
    agent_id: str,
    svc: ContextService = Depends(get_context_service),
):
    """List contexts assigned to the agent."""
    contexts = svc.get_available_contexts_for_agent(agent_id)
    return ContextListResponse(contexts=contexts)

@router.get("/{context_id}/content", response_model=ContextContentResponse)
def get_context_content(
    context_id: uuid.UUID,
    agent_id: str,
    svc: ContextService = Depends(get_context_service),
):
    """Fetch the content of an assigned context."""
    content = svc.get_context_content_for_agent(agent_id, context_id)
    context = svc.get_global_context_by_id(context_id)
    return ContextContentResponse(id=context.id, name=context.name, content=content)


# ── Manual-context RAG endpoints ────────────────────────────────────────────
# These expose the chunked + embedded manual contexts via explicit search
# and admin reindex. There is NO automatic injection into chat or voice
# prompts — callers (client UI, or a future agent tool) decide when to
# look something up and pay the token cost deliberately.


@router.post("/search", response_model=List[dict])
def search_manual_contexts(
    agent_id: str = Query(..., description="Which agent's assigned contexts to search"),
    query: str = Query(..., description="Natural-language query to match against chunks"),
    top_k: int = Query(default=manual_context_service.DEFAULT_TOP_K, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Search an agent's assigned manual contexts for relevant chunks.

    Returns the top-k chunks (by cosine similarity) with their text,
    score, and source context metadata. Returns an empty list if the
    agent has no assigned contexts or the query is empty.
    """
    return manual_context_service.search_for_agent(
        db=db, agent_id=agent_id, query=query, top_k=top_k,
    )


@router.post("/{context_id}/reindex")
def reindex_manual_context(
    context_id: uuid.UUID,
    svc: ContextService = Depends(get_context_service),
    db: Session = Depends(get_db),
):
    """Force-rebuild the Qdrant chunks for a single manual context.

    Useful for (a) retrying after an embedding failure during create/update
    and (b) debugging a specific context. Uses the current content from
    Postgres as the source of truth. For bulk backfill of pre-RAG
    contexts, use ``/reindex-all`` instead.
    """
    ctx = svc.get_global_context_by_id(context_id)
    chunk_count = manual_context_service.reindex_context(
        ctx.id, ctx.name, ctx.content
    )
    ctx.content_hash = manual_context_service.compute_content_hash(ctx.content)
    db.commit()
    db.refresh(ctx)
    return {
        "context_id": str(ctx.id),
        "name": ctx.name,
        "chunk_count": chunk_count,
        "content_hash": ctx.content_hash,
    }


@router.post("/reindex-all")
def reindex_all_unindexed_contexts(
    db: Session = Depends(get_db),
):
    """Backfill every manual context whose ``content_hash`` is NULL.

    Idempotent — running it again after a successful sweep is a no-op
    (no rows match the NULL filter). Safe to run on startup or to invoke
    explicitly after bulk-importing contexts. Embedding rate limits are
    handled inside ``embed_service`` so large corpora self-throttle.

    Returns ``{scanned, indexed, skipped, failed}``.
    """
    return manual_context_service.backfill_unindexed_contexts(db)


@router.get("/ram/context/active")
def list_active_tasks():
    """Return all in-flight context sync tasks with their live Celery state."""
    active = get_active_tasks()
    rows = []
    for key, task_id in active.items():
        parts = key.split(":")
        if len(parts) == 3:
            # New format: integration:type:agent_id
            integration_name, task_type, agent_id = parts
        elif len(parts) == 2:
            # Old format: integration:agent_id
            integration_name, agent_id = parts
            task_type = "ingest"
        else:
            # Fallback
            integration_name = "gmail"
            agent_id = key
            task_type = "ingest"

        rows.append(
            {
                "agent_id": agent_id,
                "integration": integration_name,
                "task_type": task_type,
                "task_id": task_id,
                "status": celery_app.AsyncResult(task_id).state,
            }
        )
    return rows


@router.post("/ram/context/gmail")
async def create_gmail_context(
    agent_id: str,
    force_full_sync: bool = False,
    db: Session = Depends(get_db),
):
    """Start a unified Gmail ingest + pipeline job for an agent.

    Validates that Gmail is assigned and credentials are valid, creates a
    ThirdPartyContext tracking row, and enqueues the background task.

    Set ``force_full_sync=true`` to discard any stored sync checkpoint and
    re-ingest the entire mailbox from scratch.
    """
    return await ThirdPartyContextService(db).create_context("gmail", agent_id, force_full_sync)


@router.delete("/ram/context/{context_id}/data")
async def purge_context_data(
    context_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Delete context data from S3, Qdrant, and remove the context DB row."""
    return await ThirdPartyContextService(db).purge_context_data(context_id)


@router.get("/ram/task/{task_id}/progress")
async def task_progress(task_id: str):
    """SSE stream — connect here to watch progress for any background task.

    Emits events every 0.5s so the frontend always sees liveness.
    Each event includes ``heartbeat`` (monotonic counter) and
    ``elapsed_seconds`` so the UI can show a running timer even when
    the underlying task state hasn't changed.
    """
    import time as _time

    async def event_stream():
        start = _time.monotonic()
        heartbeat = 0
        while True:
            result = celery_app.AsyncResult(task_id)
            try:
                state = result.state
                info = result.info or {}
            except Exception:
                yield f'data: {json.dumps({"task_id": task_id, "status": "FAILURE", "message": "Task failed — check worker logs for details."})}\n\n'
                break

            heartbeat += 1
            data = {
                "task_id": task_id,
                "status": state,
                "heartbeat": heartbeat,
                "elapsed_seconds": round(_time.monotonic() - start, 1),
                **(info if isinstance(info, dict) else {"message": str(info)}),
            }
            yield f"data: {json.dumps(data)}\n\n"

            if state in ("SUCCESS", "FAILURE", "REVOKED", "TASK_ERROR", "TASK_CANCELLED"):
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/ram/task/{task_id}")
def cancel_task(task_id: str):
    """Cancel any running Celery task by ID.

    Sends a cooperative abort signal (for AbortableTask-based tasks) and also
    revokes the task so it won't start if it is still queued.
    """
    AbortableAsyncResult(task_id, app=celery_app).abort()
    celery_app.control.revoke(task_id)
    state = celery_app.AsyncResult(task_id).state
    return {
        "task_id": task_id,
        "status": "cancellation requested",
        "current_state": state,
    }
