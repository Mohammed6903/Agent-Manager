"""Helpers for parsing chat requests and handling file uploads."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile

from .config import settings
from .schemas import ChatMessage, ChatRequest

logger = logging.getLogger("agent_manager.chat_helpers")

# ── File upload config ──────────────────────────────────────────────────────────

_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".tiff", ".tif", ".heic", ".heif", ".svg",
}

_ALLOWED_EXTENSIONS = {
    *_IMAGE_EXTENSIONS,
    # Documents
    ".pdf", ".txt", ".csv", ".json", ".yaml", ".yml", ".xml",
    ".md", ".html", ".htm", ".log",
    # Office
    ".doc", ".docx", ".xls", ".xlsx",
}


# ── Image compression ──────────────────────────────────────────────────────────

def _compress_image(content: bytes, target_bytes: int) -> tuple[bytes, str]:
    """Compress an image to fit within target_bytes.

    Returns (compressed_bytes, new_extension).
    Progressively reduces quality and dimensions until the target is met.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(content))

    # Convert RGBA/palette to RGB for JPEG output
    if img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Step 1: Resize if very large (cap longest edge at 2048px)
    max_dim = 2048
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    # Step 2: Try decreasing JPEG quality until under target
    result = None
    for quality in (85, 70, 55, 40, 30):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        result = buf.getvalue()
        if len(result) <= target_bytes:
            logger.info(
                "Image compressed: %dKB -> %dKB (quality=%d, size=%sx%s)",
                len(content) // 1024, len(result) // 1024, quality, *img.size,
            )
            return result, ".jpg"

    # Step 3: If still too large, progressively shrink dimensions
    for scale in (0.75, 0.5, 0.35, 0.25):
        w, h = int(img.size[0] * scale), int(img.size[1] * scale)
        if w < 100 or h < 100:
            break
        resized = img.resize((w, h), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=50, optimize=True)
        result = buf.getvalue()
        if len(result) <= target_bytes:
            logger.info(
                "Image compressed (resized): %dKB -> %dKB (size=%dx%d)",
                len(content) // 1024, len(result) // 1024, w, h,
            )
            return result, ".jpg"

    # Fallback: return the smallest version we produced
    if result is None:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=30, optimize=True)
        result = buf.getvalue()
    logger.warning(
        "Image could not be compressed below target (%dKB)", len(result) // 1024
    )
    return result, ".jpg"


# ── File saving ─────────────────────────────────────────────────────────────────

def _uploads_dir(agent_id: str) -> Path:
    """Return the uploads directory for an agent's workspace."""
    return Path(settings.OPENCLAW_STATE_DIR) / f"workspace-{agent_id}" / "uploads"


async def save_upload(agent_id: str, file: UploadFile) -> str:
    """Save an uploaded file to the agent's workspace and return the path.

    Images are auto-compressed to fit within MAX_UPLOAD_SIZE_MB.
    Non-image files that exceed the limit are rejected with a 413 error.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_file_type",
                "message": f"File type '{ext}' is not supported.",
                "allowed": sorted(_ALLOWED_EXTENSIONS),
            },
        )

    # Read file content
    max_raw_bytes = settings.MAX_RAW_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()

    # Reject files that exceed the raw upload limit
    if len(content) > max_raw_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "file_too_large",
                "message": (
                    f"File size ({len(content) / 1024 / 1024:.1f}MB) exceeds the "
                    f"{settings.MAX_RAW_UPLOAD_SIZE_MB}MB upload limit."
                ),
                "max_size_mb": settings.MAX_RAW_UPLOAD_SIZE_MB,
            },
        )

    is_image = ext in _IMAGE_EXTENSIONS and ext != ".svg"
    target_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    save_name = file.filename

    # Auto-compress images that exceed the target size
    if is_image and len(content) > target_bytes:
        logger.info(
            "Compressing image %s (%dKB) to fit under %dMB",
            file.filename, len(content) // 1024, settings.MAX_UPLOAD_SIZE_MB,
        )
        content, new_ext = await asyncio.to_thread(
            _compress_image, content, target_bytes
        )
        base_name = os.path.splitext(file.filename)[0]
        save_name = f"{base_name}{new_ext}"
    elif not is_image and len(content) > target_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "file_too_large",
                "message": (
                    f"File size ({len(content) / 1024 / 1024:.1f}MB) exceeds the "
                    f"{settings.MAX_UPLOAD_SIZE_MB}MB limit. Only images are auto-compressed."
                ),
                "max_size_mb": settings.MAX_UPLOAD_SIZE_MB,
            },
        )

    # Generate unique filename to avoid collisions
    unique_name = f"{uuid.uuid4().hex[:12]}_{save_name}"
    upload_dir = _uploads_dir(agent_id)
    await asyncio.to_thread(os.makedirs, str(upload_dir), exist_ok=True)

    filepath = upload_dir / unique_name
    await asyncio.to_thread(filepath.write_bytes, content)

    logger.info("Saved upload: %s (%d bytes)", filepath, len(content))
    return str(filepath)


# ── Request parsing ─────────────────────────────────────────────────────────────

async def parse_chat_request(
    request: Request,
) -> tuple[ChatRequest, list[str] | None]:
    """Parse a chat request from either JSON or multipart form data.

    Returns (ChatRequest, file_paths) where file_paths is None when
    no files were uploaded.

    - **JSON body** (Content-Type: application/json):
        Standard ``ChatRequest`` fields.
    - **Multipart form** (Content-Type: multipart/form-data):
        Form fields matching ``ChatRequest`` + optional ``files``.
        ``history`` is accepted as a JSON-encoded string.
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        return await _parse_multipart(request)

    # Default: JSON body (preserves backward compatibility)
    body = await request.json()
    req = ChatRequest(**body)
    return req, None


async def _parse_multipart(
    request: Request,
) -> tuple[ChatRequest, list[str] | None]:
    """Parse multipart form data into a ChatRequest + uploaded file paths."""
    form = await request.form()

    # Required fields
    message = form.get("message")
    agent_id = form.get("agent_id")
    user_id = form.get("user_id")

    if not message or not agent_id or not user_id:
        raise HTTPException(
            status_code=400,
            detail="Fields 'message', 'agent_id', and 'user_id' are required.",
        )

    # Optional fields
    session_id = form.get("session_id") or None
    room_id = form.get("room_id") or None
    recent_context = form.get("recent_context") or None
    history_raw = form.get("history") or None

    # Parse history JSON string
    history: list[ChatMessage] = []
    if history_raw:
        try:
            parsed = json.loads(str(history_raw))
            history = [ChatMessage(**m) for m in parsed]
        except Exception:
            logger.warning("Could not parse history JSON, ignoring: %s", history_raw)

    req = ChatRequest(
        message=str(message),
        agent_id=str(agent_id),
        user_id=str(user_id),
        session_id=str(session_id) if session_id else None,
        room_id=str(room_id) if room_id else None,
        recent_context=str(recent_context) if recent_context else None,
        history=history,
    )

    # Collect uploaded files
    file_paths: list[str] = []
    for key in form:
        value = form.getlist(key)
        for item in value:
            if isinstance(item, UploadFile) and item.filename:
                path = await save_upload(req.agent_id, item)
                file_paths.append(path)

    return req, file_paths if file_paths else None
