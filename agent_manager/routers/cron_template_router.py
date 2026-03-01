from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.cron_template import (
    CronTemplateCreate,
    CronTemplateUpdate,
    CronTemplateResponse,
    CronTemplateInstantiateRequest
)
from ..services.cron_template_service import CronTemplateService
from ..dependencies import get_gateway
from ..clients.gateway_client import GatewayClient

router = APIRouter(tags=["Cron Templates"])

def get_cron_template_service(
    db: Session = Depends(get_db),
    gateway: GatewayClient = Depends(get_gateway)
) -> CronTemplateService:
    return CronTemplateService(db, gateway)

@router.post("", response_model=CronTemplateResponse, status_code=201)
def create_cron_template(
    req: CronTemplateCreate,
    user_id: str,
    svc: CronTemplateService = Depends(get_cron_template_service)
):
    """Create a new cron template."""
    return svc.create_template(user_id, req)

@router.get("", response_model=List[CronTemplateResponse])
def list_cron_templates(
    user_id: str,
    svc: CronTemplateService = Depends(get_cron_template_service)
):
    """List all cron templates available to the user (owned + public)."""
    return svc.list_templates(user_id)

@router.get("/{template_id}", response_model=CronTemplateResponse)
def get_cron_template(
    template_id: str,
    user_id: str,
    svc: CronTemplateService = Depends(get_cron_template_service)
):
    """Get a specific cron template."""
    return svc.get_template(template_id, user_id)

@router.patch("/{template_id}", response_model=CronTemplateResponse)
def update_cron_template(
    template_id: str,
    req: CronTemplateUpdate,
    user_id: str,
    svc: CronTemplateService = Depends(get_cron_template_service)
):
    """Update a specific cron template (Owner only)."""
    return svc.update_template(template_id, user_id, req)

@router.delete("/{template_id}", status_code=204)
def delete_cron_template(
    template_id: str,
    user_id: str,
    svc: CronTemplateService = Depends(get_cron_template_service)
):
    """Delete a specific cron template (Owner only)."""
    svc.delete_template(template_id, user_id)

@router.post("/{template_id}/instantiate", status_code=201)
async def instantiate_cron_template(
    template_id: str,
    req: CronTemplateInstantiateRequest,
    svc: CronTemplateService = Depends(get_cron_template_service)
):
    """Create a real cron job from a template by binding variables."""
    return await svc.instantiate_template(template_id, req)
