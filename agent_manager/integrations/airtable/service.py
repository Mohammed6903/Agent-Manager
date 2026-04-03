"""Airtable operations service."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "airtable"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


async def list_bases(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/meta/bases")
        resp.raise_for_status()
        return resp.json()


async def list_tables(db: Session, agent_id: str, base_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/meta/bases/{base_id}/tables")
        resp.raise_for_status()
        return resp.json()


async def list_records(
    db: Session, agent_id: str, base_id: str, table_id_or_name: str,
    max_records: Optional[int] = None, view: Optional[str] = None,
    filter_by_formula: Optional[str] = None, offset: Optional[str] = None,
):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if max_records is not None:
        params["maxRecords"] = max_records
    if view is not None:
        params["view"] = view
    if filter_by_formula is not None:
        params["filterByFormula"] = filter_by_formula
    if offset is not None:
        params["offset"] = offset
    async with client:
        resp = await client.get(f"{client.base_url}/{base_id}/{table_id_or_name}", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_record(db: Session, agent_id: str, base_id: str, table_id_or_name: str, record_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/{base_id}/{table_id_or_name}/{record_id}")
        resp.raise_for_status()
        return resp.json()


async def create_records(
    db: Session, agent_id: str, base_id: str, table_id_or_name: str,
    records: List[Dict[str, Any]],
):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(
            f"{client.base_url}/{base_id}/{table_id_or_name}",
            json={"records": records},
        )
        resp.raise_for_status()
        return resp.json()


async def update_records(
    db: Session, agent_id: str, base_id: str, table_id_or_name: str,
    records: List[Dict[str, Any]],
):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.patch(
            f"{client.base_url}/{base_id}/{table_id_or_name}",
            json={"records": records},
        )
        resp.raise_for_status()
        return resp.json()


async def delete_records(
    db: Session, agent_id: str, base_id: str, table_id_or_name: str,
    record_ids: List[str],
):
    client = await _get_client(db, agent_id)
    params = [("records[]", rid) for rid in record_ids]
    async with client:
        resp = await client.delete(f"{client.base_url}/{base_id}/{table_id_or_name}", params=params)
        resp.raise_for_status()
        return resp.json()
