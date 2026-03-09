from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
from .gmail_auth_service import get_valid_credentials
from ..integrations.sdk_logger import log_integration_call

def get_service(db: Session, agent_id: str):
    creds = get_valid_credentials(db, agent_id)
    if not creds:
        return None
    return build("meet", "v2", credentials=creds)

@log_integration_call("google_meet", "POST", "/spaces")
def create_space(db: Session, agent_id: str, config: Optional[Dict[str, Any]] = None):
    """Creates a Google Meet space."""
    service = get_service(db, agent_id)
    if not service:
        return None
    
    body = {"config": config} if config else {}
    result = service.spaces().create(body=body).execute()
    return result

@log_integration_call("google_meet", "GET", "/spaces/{name}")
def get_space(db: Session, agent_id: str, space_id: str):
    """Gets details about a specific Meet space (name format: 'spaces/xyz')."""
    service = get_service(db, agent_id)
    if not service:
        return None
    
    # Ensure name is in correct format
    name = space_id if space_id.startswith("spaces/") else f"spaces/{space_id}"
    return service.spaces().get(name=name).execute()