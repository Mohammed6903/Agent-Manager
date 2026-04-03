"""Buffer operations service."""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "buffer"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


async def api_request(
    db: Session,
    agent_id: str,
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
):
    """Generic API request for Buffer."""
    client = await _get_client(db, agent_id)
    url = f"{client.base_url}{path}"
    kwargs: Dict[str, Any] = {}
    if params:
        kwargs["params"] = params
    if json_body:
        kwargs["json"] = json_body
    if data:
        kwargs["data"] = data
    async with client:
        resp = await client.request(method, url, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {"status": "success"}
        return resp.json()
