"""HubSpot CRM endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    HubSpotListRequest,
    HubSpotObjectIdRequest,
    HubSpotCreateObjectRequest,
    HubSpotUpdateObjectRequest,
    HubSpotSearchRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

@router.post("/contacts/list", tags=["HubSpot"])
async def list_contacts(body: HubSpotListRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_contacts(db, body.agent_id, limit=body.limit, after=body.after)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contacts/get", tags=["HubSpot"])
async def get_contact(body: HubSpotObjectIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_contact(db, body.agent_id, body.object_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contacts/create", tags=["HubSpot"])
async def create_contact(body: HubSpotCreateObjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_contact(db, body.agent_id, body.properties)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/contacts/{contact_id}", tags=["HubSpot"])
async def update_contact(contact_id: str, body: HubSpotUpdateObjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_contact(db, body.agent_id, contact_id, body.properties)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contacts/search", tags=["HubSpot"])
async def search_contacts(body: HubSpotSearchRequest, db: Session = Depends(get_db)):
    try:
        return await service.search_contacts(
            db, body.agent_id, filter_groups=body.filter_groups,
            sorts=body.sorts, query=body.query, limit=body.limit, after=body.after,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

@router.post("/companies/list", tags=["HubSpot"])
async def list_companies(body: HubSpotListRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_companies(db, body.agent_id, limit=body.limit, after=body.after)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/companies/get", tags=["HubSpot"])
async def get_company(body: HubSpotObjectIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_company(db, body.agent_id, body.object_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/companies/create", tags=["HubSpot"])
async def create_company(body: HubSpotCreateObjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_company(db, body.agent_id, body.properties)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/companies/{company_id}", tags=["HubSpot"])
async def update_company(company_id: str, body: HubSpotUpdateObjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_company(db, body.agent_id, company_id, body.properties)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/companies/search", tags=["HubSpot"])
async def search_companies(body: HubSpotSearchRequest, db: Session = Depends(get_db)):
    try:
        return await service.search_companies(
            db, body.agent_id, filter_groups=body.filter_groups,
            sorts=body.sorts, query=body.query, limit=body.limit, after=body.after,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------

@router.post("/deals/list", tags=["HubSpot"])
async def list_deals(body: HubSpotListRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_deals(db, body.agent_id, limit=body.limit, after=body.after)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deals/get", tags=["HubSpot"])
async def get_deal(body: HubSpotObjectIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_deal(db, body.agent_id, body.object_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deals/create", tags=["HubSpot"])
async def create_deal(body: HubSpotCreateObjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_deal(db, body.agent_id, body.properties)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/deals/{deal_id}", tags=["HubSpot"])
async def update_deal(deal_id: str, body: HubSpotUpdateObjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_deal(db, body.agent_id, deal_id, body.properties)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deals/search", tags=["HubSpot"])
async def search_deals(body: HubSpotSearchRequest, db: Session = Depends(get_db)):
    try:
        return await service.search_deals(
            db, body.agent_id, filter_groups=body.filter_groups,
            sorts=body.sorts, query=body.query, limit=body.limit, after=body.after,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

@router.post("/tickets/list", tags=["HubSpot"])
async def list_tickets(body: HubSpotListRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_tickets(db, body.agent_id, limit=body.limit, after=body.after)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickets/get", tags=["HubSpot"])
async def get_ticket(body: HubSpotObjectIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_ticket(db, body.agent_id, body.object_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickets/create", tags=["HubSpot"])
async def create_ticket(body: HubSpotCreateObjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_ticket(db, body.agent_id, body.properties)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tickets/{ticket_id}", tags=["HubSpot"])
async def update_ticket(ticket_id: str, body: HubSpotUpdateObjectRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_ticket(db, body.agent_id, ticket_id, body.properties)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Owners
# ---------------------------------------------------------------------------

@router.post("/owners/list", tags=["HubSpot"])
async def list_owners(body: HubSpotListRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_owners(db, body.agent_id, limit=body.limit, after=body.after)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/owners/get", tags=["HubSpot"])
async def get_owner(body: HubSpotObjectIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_owner(db, body.agent_id, body.object_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
