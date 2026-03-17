"""Agent Secrets management router."""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.gmail import AgentSecret
from ..security import encrypt, decrypt
from agent_manager.integrations.google.schemas import SecretUpsertRequest

router = APIRouter()

def _encrypt_secret_data(data: Dict[str, Any]) -> Dict[str, str]:
    """Encrypt every value in the dict with Fernet."""
    return {k: encrypt(str(v)) for k, v in data.items()}

def _decrypt_secret_data(data: Dict[str, Any]) -> Dict[str, str]:
    """Decrypt every value in the dict with Fernet."""
    return {k: decrypt(str(v)) for k, v in data.items()}

@router.post("/", tags=["Secrets"])
def upsert_secret(body: SecretUpsertRequest, db: Session = Depends(get_db)):
    """Create or update a secret for an agent + service combination."""
    encrypted = _encrypt_secret_data(body.secret_data)

    secret = (
        db.query(AgentSecret)
        .filter(AgentSecret.agent_id == body.agent_id, AgentSecret.service_name == body.service_name)
        .first()
    )
    if secret:
        secret.secret_data = encrypted
    else:
        secret = AgentSecret(
            agent_id=body.agent_id,
            service_name=body.service_name,
            secret_data=encrypted,
        )
        db.add(secret)

    db.commit()
    db.refresh(secret)
    return {
        "id": secret.id,
        "agent_id": secret.agent_id,
        "service_name": secret.service_name,
        "updated_at": secret.updated_at,
    }

@router.get("/{agent_id}", tags=["Secrets"])
def list_secrets(agent_id: str, db: Session = Depends(get_db)):
    """List all secrets for a given agent (returns service names only, not the data)."""
    secrets = db.query(AgentSecret).filter(AgentSecret.agent_id == agent_id).all()
    return [
        {
            "id": s.id,
            "service_name": s.service_name,
            "updated_at": s.updated_at,
        }
        for s in secrets
    ]

@router.get("/{agent_id}/{service_name}", tags=["Secrets"])
def get_secret(agent_id: str, service_name: str, db: Session = Depends(get_db)):
    """Get the full secret data for an agent + service."""
    secret = (
        db.query(AgentSecret)
        .filter(AgentSecret.agent_id == agent_id, AgentSecret.service_name == service_name)
        .first()
    )
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    return {
        "id": secret.id,
        "agent_id": secret.agent_id,
        "service_name": secret.service_name,
        "secret_data": _decrypt_secret_data(secret.secret_data),
        "updated_at": secret.updated_at,
    }

@router.delete("/{agent_id}/{service_name}", tags=["Secrets"])
def delete_secret(agent_id: str, service_name: str, db: Session = Depends(get_db)):
    """Delete a secret for an agent + service."""
    secret = (
        db.query(AgentSecret)
        .filter(AgentSecret.agent_id == agent_id, AgentSecret.service_name == service_name)
        .first()
    )
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    db.delete(secret)
    db.commit()
    return {"status": "deleted"}
