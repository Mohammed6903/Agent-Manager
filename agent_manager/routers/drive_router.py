"""Google Drive endpoints router."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
import base64

from ..database import get_db
from ..services import drive_service
from ..schemas.google import ShareFileRequest, MoveFileRequest, RenameFileRequest, CreateFolderRequest

router = APIRouter()


@router.post("/files", tags=["Google Drive"])
async def upload_drive_file(request: Request, db: Session = Depends(get_db)):
    """
    Upload a file to Google Drive.

    Accepts either:
    - **multipart/form-data**: fields `agent_id`, `file` (binary), optional `parent_id`
    - **JSON body**: `{ agent_id, filename, content, mime_type?, parent_id?, encoding? }`
      where `content` is UTF-8 text or base64-encoded bytes (set `encoding: "base64"`).
    """
    content_type = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            agent_id = form["agent_id"]
            upload = form["file"]
            parent_id = form.get("parent_id")
            file_content = await upload.read()
            mime_type = upload.content_type or "application/octet-stream"
            filename = upload.filename
        else:
            body = await request.json()
            agent_id = body["agent_id"]
            filename = body["filename"]
            parent_id = body.get("parent_id")
            mime_type = body.get("mime_type", "text/plain")
            raw = body.get("content", "")
            if body.get("encoding") == "base64":
                file_content = base64.b64decode(raw)
            else:
                file_content = raw.encode("utf-8") if isinstance(raw, str) else raw

        result = drive_service.upload_file(
            db, agent_id,
            filename=filename,
            content=file_content,
            mime_type=mime_type,
            parent_id=parent_id,
        )
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"status": "uploaded", "file": result}
    except HTTPException:
        raise
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"Missing required field: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files", tags=["Google Drive"])
def list_drive_files(
    agent_id: str,
    max_results: int = 20,
    query: str = None,
    folder_id: str = None,
    db: Session = Depends(get_db),
):
    """List files in Drive. `query` is a raw Google Drive query string (e.g. `name contains 'foo'`)."""
    try:
        files = drive_service.list_files(db, agent_id, max_results=max_results, query=query, folder_id=folder_id)
        if files is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"files": files}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/download", tags=["Google Drive"])
def download_drive_file(
    agent_id: str,
    file_id: str,
    mime_type: str = None,
    db: Session = Depends(get_db),
):
    """
    Download or export a file's content.

    - Regular files: returned as raw bytes with their native MIME type.
    - Google Workspace files (Docs, Sheets, Slides): exported to `mime_type` if
      provided, otherwise a sensible default is chosen (text/plain for Docs,
      text/csv for Sheets, etc.).
    """
    try:
        result = drive_service.download_file(db, agent_id, file_id, mime_type=mime_type)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        filename = result["filename"].replace('"', '\\"')
        return Response(
            content=result["content"],
            media_type=result["mime_type"],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{file_id}", tags=["Google Drive"])
def get_drive_file(agent_id: str, file_id: str, db: Session = Depends(get_db)):
    """Get metadata for a specific file."""
    try:
        file = drive_service.get_file(db, agent_id, file_id)
        if file is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return file
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folders", tags=["Google Drive"])
def list_drive_folders(
    agent_id: str,
    max_results: int = 50,
    parent_id: str = None,
    db: Session = Depends(get_db),
):
    """List all folders in Drive, optionally scoped to a parent folder."""
    try:
        q = "mimeType = 'application/vnd.google-apps.folder'"
        files = drive_service.list_files(db, agent_id, max_results=max_results, query=q, folder_id=parent_id)
        if files is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"folders": files}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folders", tags=["Google Drive"])
def create_drive_folder(body: CreateFolderRequest, db: Session = Depends(get_db)):
    """Create a new folder in Drive."""
    try:
        folder = drive_service.create_folder(db, body.agent_id, body.name, parent_id=body.parent_id)
        if folder is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return {"status": "created", "folder": folder}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/folders/{folder_id}", tags=["Google Drive"])
def delete_drive_folder(agent_id: str, folder_id: str, db: Session = Depends(get_db)):
    """Delete a folder (moves to trash)."""
    try:
        result = drive_service.delete_file(db, agent_id, folder_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/folders/{folder_id}/rename", tags=["Google Drive"])
def rename_drive_folder(folder_id: str, body: RenameFileRequest, db: Session = Depends(get_db)):
    """Rename a folder."""
    try:
        result = drive_service.rename_file(db, body.agent_id, folder_id, body.new_name)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/folders/{folder_id}/move", tags=["Google Drive"])
def move_drive_folder(folder_id: str, body: MoveFileRequest, db: Session = Depends(get_db)):
    """Move a folder into another folder."""
    try:
        result = drive_service.move_file(db, body.agent_id, folder_id, body.new_parent_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/files/{file_id}", tags=["Google Drive"])
def delete_drive_file(agent_id: str, file_id: str, db: Session = Depends(get_db)):
    """Move a file to trash."""
    try:
        result = drive_service.delete_file(db, agent_id, file_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/files/{file_id}/move", tags=["Google Drive"])
def move_drive_file(file_id: str, body: MoveFileRequest, db: Session = Depends(get_db)):
    """Move a file to a different folder."""
    try:
        result = drive_service.move_file(db, body.agent_id, file_id, body.new_parent_id)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/files/{file_id}/rename", tags=["Google Drive"])
def rename_drive_file(file_id: str, body: RenameFileRequest, db: Session = Depends(get_db)):
    """Rename a file or folder."""
    try:
        result = drive_service.rename_file(db, body.agent_id, file_id, body.new_name)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files/{file_id}/share", tags=["Google Drive"])
def share_drive_file(file_id: str, body: ShareFileRequest, db: Session = Depends(get_db)):
    """Share a file with a specific user."""
    try:
        result = drive_service.share_file(db, body.agent_id, file_id, body.email, role=body.role)
        if result is None:
            raise HTTPException(status_code=401, detail="Agent not authenticated or token expired")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
