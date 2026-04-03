from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
from agent_manager.integrations.google.gmail.auth_service import get_valid_credentials


def get_service(db: Session, agent_id: str):
    creds = get_valid_credentials(db, agent_id)
    if not creds:
        return None
    return build("googleads", "v16", credentials=creds)
