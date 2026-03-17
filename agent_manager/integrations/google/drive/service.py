"""Google Drive operations service."""

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from sqlalchemy.orm import Session
from typing import Optional
import io

from agent_manager.integrations.google.gmail.auth_service import get_valid_credentials
from agent_manager.integrations.sdk_logger import log_integration_call

# Google Workspace MIME types that require export instead of direct download
_WORKSPACE_EXPORT_DEFAULTS = {
    "application/vnd.google-apps.document":     "text/plain",
    "application/vnd.google-apps.spreadsheet":  "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.drawing":      "image/png",
}


def get_service(db: Session, agent_id: str):
    creds = get_valid_credentials(db, agent_id)
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)


@log_integration_call("google_drive", "GET", "/files")
def list_files(db: Session, agent_id: str, max_results: int = 20, query: Optional[str] = None, folder_id: Optional[str] = None):
    """List files in Drive.
    
    `query` is a raw Google Drive query string (e.g. "name contains 'foo' and mimeType = 'application/vnd.google-apps.folder'").
    `folder_id` is a convenience param that appends a parent-folder filter.
    `trashed = false` is always appended unless the query already contains it.
    """
    service = get_service(db, agent_id)
    if not service:
        return None

    q_parts = []
    if query:
        q_parts.append(f"({query})")
    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")
    combined = " and ".join(q_parts)
    if "trashed" not in combined:
        q_parts.append("trashed = false")
        combined = " and ".join(q_parts)

    results = service.files().list(
        pageSize=max_results,
        q=combined,
        fields="files(id, name, mimeType, size, modifiedTime, webViewLink, parents)",
    ).execute()

    return results.get("files", [])


@log_integration_call("google_drive", "GET", "/files/{fileId}")
def get_file(db: Session, agent_id: str, file_id: str):
    """Get metadata for a specific file."""
    service = get_service(db, agent_id)
    if not service:
        return None

    return service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, size, modifiedTime, webViewLink, parents, description",
    ).execute()


@log_integration_call("google_drive", "POST", "/files")
def create_folder(db: Session, agent_id: str, name: str, parent_id: Optional[str] = None):
    """Create a new folder in Drive."""
    service = get_service(db, agent_id)
    if not service:
        return None

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    return service.files().create(body=metadata, fields="id, name, webViewLink").execute()


@log_integration_call("google_drive", "DELETE", "/files/{fileId}")
def delete_file(db: Session, agent_id: str, file_id: str):
    """Move a file to trash."""
    service = get_service(db, agent_id)
    if not service:
        return None

    service.files().delete(fileId=file_id).execute()
    return {"deleted": file_id}


@log_integration_call("google_drive", "PATCH", "/files/{fileId}")
def move_file(db: Session, agent_id: str, file_id: str, new_parent_id: str):
    """Move a file to a different folder."""
    service = get_service(db, agent_id)
    if not service:
        return None

    file = service.files().get(fileId=file_id, fields="parents").execute()
    previous_parents = ",".join(file.get("parents", []))

    return service.files().update(
        fileId=file_id,
        addParents=new_parent_id,
        removeParents=previous_parents,
        fields="id, name, parents",
    ).execute()


@log_integration_call("google_drive", "PATCH", "/files/{fileId}")
def rename_file(db: Session, agent_id: str, file_id: str, new_name: str):
    """Rename a file or folder."""
    service = get_service(db, agent_id)
    if not service:
        return None

    return service.files().update(
        fileId=file_id,
        body={"name": new_name},
        fields="id, name",
    ).execute()


@log_integration_call("google_drive", "POST", "/files/{fileId}/permissions")
def share_file(db: Session, agent_id: str, file_id: str, email: str, role: str = "reader"):
    """Share a file with a specific user. role: reader | commenter | writer"""
    service = get_service(db, agent_id)
    if not service:
        return None

    permission = {
        "type": "user",
        "role": role,
        "emailAddress": email,
    }
    return service.permissions().create(
        fileId=file_id,
        body=permission,
        fields="id, role, emailAddress",
    ).execute()


@log_integration_call("google_drive", "GET", "/files/{fileId} (download)")
def download_file(db: Session, agent_id: str, file_id: str, mime_type: Optional[str] = None) -> Optional[dict]:
    """
    Download or export a file's content.

    - For regular files: downloads binary content directly.
    - For Google Workspace files (Docs, Sheets, etc.): exports to the requested
      mime_type, or falls back to a sensible default (text/plain for Docs, text/csv
      for Sheets, etc.).

    Returns a dict with keys: `content` (bytes), `mime_type` (str), `filename` (str).
    """
    service = get_service(db, agent_id)
    if not service:
        return None

    # Fetch file metadata to know its native mimeType and name
    meta = service.files().get(
        fileId=file_id,
        fields="id, name, mimeType",
    ).execute()

    native_mime = meta.get("mimeType", "")
    filename = meta.get("name", file_id)

    if native_mime in _WORKSPACE_EXPORT_DEFAULTS:
        # Google Workspace file — must use export()
        export_mime = mime_type or _WORKSPACE_EXPORT_DEFAULTS[native_mime]
        response = service.files().export(
            fileId=file_id,
            mimeType=export_mime,
        ).execute()
        # export() returns bytes directly
        content = response if isinstance(response, bytes) else response.encode("utf-8", errors="replace")
        return {"content": content, "mime_type": export_mime, "filename": filename}
    else:
        # Regular binary file — use get_media()
        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return {"content": buf.getvalue(), "mime_type": mime_type or native_mime, "filename": filename}


@log_integration_call("google_drive", "POST", "/files (upload)")
def upload_file(
    db: Session,
    agent_id: str,
    filename: str,
    content: bytes,
    mime_type: str,
    parent_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Upload a file to Google Drive.

    Args:
        filename:  Name the file will have in Drive.
        content:   Raw file bytes.
        mime_type: MIME type of the content (e.g. 'text/plain', 'application/pdf').
        parent_id: Optional folder ID to place the file in.
    """
    service = get_service(db, agent_id)
    if not service:
        return None

    metadata: dict = {"name": filename}
    if parent_id:
        metadata["parents"] = [parent_id]

    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
    result = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, mimeType, webViewLink, parents",
    ).execute()
    return result
