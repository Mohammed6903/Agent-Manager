"""HubSpot CRM operations service."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "hubspot"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


async def _list_objects(db, agent_id, object_type, limit=None, after=None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if after is not None:
        params["after"] = after
    async with client:
        resp = await client.get(f"{client.base_url}/crm/v3/objects/{object_type}", params=params)
        resp.raise_for_status()
        return resp.json()


async def _get_object(db, agent_id, object_type, object_id):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/crm/v3/objects/{object_type}/{object_id}")
        resp.raise_for_status()
        return resp.json()


async def _create_object(db, agent_id, object_type, properties):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(
            f"{client.base_url}/crm/v3/objects/{object_type}",
            json={"properties": properties},
        )
        resp.raise_for_status()
        return resp.json()


async def _update_object(db, agent_id, object_type, object_id, properties):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.patch(
            f"{client.base_url}/crm/v3/objects/{object_type}/{object_id}",
            json={"properties": properties},
        )
        resp.raise_for_status()
        return resp.json()


async def _search_objects(db, agent_id, object_type, filter_groups=None, sorts=None, query=None, limit=None, after=None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if filter_groups is not None:
        payload["filterGroups"] = filter_groups
    if sorts is not None:
        payload["sorts"] = sorts
    if query is not None:
        payload["query"] = query
    if limit is not None:
        payload["limit"] = limit
    if after is not None:
        payload["after"] = after
    async with client:
        resp = await client.post(f"{client.base_url}/crm/v3/objects/{object_type}/search", json=payload)
        resp.raise_for_status()
        return resp.json()


# Contacts
async def list_contacts(db, agent_id, limit=None, after=None):
    return await _list_objects(db, agent_id, "contacts", limit, after)

async def get_contact(db, agent_id, contact_id):
    return await _get_object(db, agent_id, "contacts", contact_id)

async def create_contact(db, agent_id, properties):
    return await _create_object(db, agent_id, "contacts", properties)

async def update_contact(db, agent_id, contact_id, properties):
    return await _update_object(db, agent_id, "contacts", contact_id, properties)

async def search_contacts(db, agent_id, filter_groups=None, sorts=None, query=None, limit=None, after=None):
    return await _search_objects(db, agent_id, "contacts", filter_groups, sorts, query, limit, after)


# Companies
async def list_companies(db, agent_id, limit=None, after=None):
    return await _list_objects(db, agent_id, "companies", limit, after)

async def get_company(db, agent_id, company_id):
    return await _get_object(db, agent_id, "companies", company_id)

async def create_company(db, agent_id, properties):
    return await _create_object(db, agent_id, "companies", properties)

async def update_company(db, agent_id, company_id, properties):
    return await _update_object(db, agent_id, "companies", company_id, properties)

async def search_companies(db, agent_id, filter_groups=None, sorts=None, query=None, limit=None, after=None):
    return await _search_objects(db, agent_id, "companies", filter_groups, sorts, query, limit, after)


# Deals
async def list_deals(db, agent_id, limit=None, after=None):
    return await _list_objects(db, agent_id, "deals", limit, after)

async def get_deal(db, agent_id, deal_id):
    return await _get_object(db, agent_id, "deals", deal_id)

async def create_deal(db, agent_id, properties):
    return await _create_object(db, agent_id, "deals", properties)

async def update_deal(db, agent_id, deal_id, properties):
    return await _update_object(db, agent_id, "deals", deal_id, properties)

async def search_deals(db, agent_id, filter_groups=None, sorts=None, query=None, limit=None, after=None):
    return await _search_objects(db, agent_id, "deals", filter_groups, sorts, query, limit, after)


# Tickets
async def list_tickets(db, agent_id, limit=None, after=None):
    return await _list_objects(db, agent_id, "tickets", limit, after)

async def get_ticket(db, agent_id, ticket_id):
    return await _get_object(db, agent_id, "tickets", ticket_id)

async def create_ticket(db, agent_id, properties):
    return await _create_object(db, agent_id, "tickets", properties)

async def update_ticket(db, agent_id, ticket_id, properties):
    return await _update_object(db, agent_id, "tickets", ticket_id, properties)


# Owners
async def list_owners(db: Session, agent_id: str, limit: Optional[int] = None, after: Optional[str] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if after is not None:
        params["after"] = after
    async with client:
        resp = await client.get(f"{client.base_url}/crm/v3/owners", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_owner(db: Session, agent_id: str, owner_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/crm/v3/owners/{owner_id}")
        resp.raise_for_status()
        return resp.json()
