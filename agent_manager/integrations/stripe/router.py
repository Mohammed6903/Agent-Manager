"""Stripe endpoints router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from . import service
from .schemas import (
    StripeAgentRequest,
    StripeListRequest,
    StripeCustomerIdRequest,
    StripeCreateCustomerRequest,
    StripeUpdateCustomerRequest,
    StripeCustomerFilterRequest,
    StripePaymentIntentIdRequest,
    StripeCreatePaymentIntentRequest,
    StripeInvoiceIdRequest,
    StripeCreateInvoiceRequest,
    StripeSubscriptionIdRequest,
    StripeCreateSubscriptionRequest,
    StripeProductIdRequest,
    StripeCreateProductRequest,
    StripeCreatePriceRequest,
)

router = APIRouter()


# Balance
@router.post("/balance", tags=["Stripe"])
async def get_balance(body: StripeAgentRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_balance(db, body.agent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Customers
@router.post("/customers/list", tags=["Stripe"])
async def list_customers(body: StripeListRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_customers(db, body.agent_id, limit=body.limit, starting_after=body.starting_after)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/customers/get", tags=["Stripe"])
async def get_customer(body: StripeCustomerIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_customer(db, body.agent_id, body.customer_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/customers/create", tags=["Stripe"])
async def create_customer(body: StripeCreateCustomerRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_customer(db, body.agent_id, email=body.email, name=body.name, metadata=body.metadata)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/customers/update/{customer_id}", tags=["Stripe"])
async def update_customer(customer_id: str, body: StripeUpdateCustomerRequest, db: Session = Depends(get_db)):
    try:
        return await service.update_customer(db, body.agent_id, customer_id, email=body.email, name=body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Payment Intents
@router.post("/payment_intents/list", tags=["Stripe"])
async def list_payment_intents(body: StripeCustomerFilterRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_payment_intents(db, body.agent_id, limit=body.limit, customer=body.customer)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payment_intents/get", tags=["Stripe"])
async def get_payment_intent(body: StripePaymentIntentIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_payment_intent(db, body.agent_id, body.payment_intent_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payment_intents/create", tags=["Stripe"])
async def create_payment_intent(body: StripeCreatePaymentIntentRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_payment_intent(db, body.agent_id, body.amount, body.currency, customer=body.customer)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Invoices
@router.post("/invoices/list", tags=["Stripe"])
async def list_invoices(body: StripeCustomerFilterRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_invoices(db, body.agent_id, limit=body.limit, customer=body.customer)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invoices/get", tags=["Stripe"])
async def get_invoice(body: StripeInvoiceIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_invoice(db, body.agent_id, body.invoice_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invoices/create", tags=["Stripe"])
async def create_invoice(body: StripeCreateInvoiceRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_invoice(db, body.agent_id, body.customer, auto_advance=body.auto_advance)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Subscriptions
@router.post("/subscriptions/list", tags=["Stripe"])
async def list_subscriptions(body: StripeCustomerFilterRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_subscriptions(db, body.agent_id, limit=body.limit, customer=body.customer)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscriptions/get", tags=["Stripe"])
async def get_subscription(body: StripeSubscriptionIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_subscription(db, body.agent_id, body.subscription_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscriptions/create", tags=["Stripe"])
async def create_subscription(body: StripeCreateSubscriptionRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_subscription(db, body.agent_id, body.customer, body.price)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/subscriptions/{subscription_id}", tags=["Stripe"])
async def cancel_subscription(agent_id: str, subscription_id: str, db: Session = Depends(get_db)):
    try:
        return await service.cancel_subscription(db, agent_id, subscription_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Products
@router.post("/products/list", tags=["Stripe"])
async def list_products(body: StripeListRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_products(db, body.agent_id, limit=body.limit)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/products/get", tags=["Stripe"])
async def get_product(body: StripeProductIdRequest, db: Session = Depends(get_db)):
    try:
        return await service.get_product(db, body.agent_id, body.product_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/products/create", tags=["Stripe"])
async def create_product(body: StripeCreateProductRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_product(db, body.agent_id, body.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Prices
@router.post("/prices/list", tags=["Stripe"])
async def list_prices(body: StripeCustomerFilterRequest, db: Session = Depends(get_db)):
    try:
        return await service.list_prices(db, body.agent_id, limit=body.limit, product=body.customer)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prices/create", tags=["Stripe"])
async def create_price(body: StripeCreatePriceRequest, db: Session = Depends(get_db)):
    try:
        return await service.create_price(
            db, body.agent_id, body.product, body.unit_amount, body.currency,
            recurring_interval=body.recurring_interval,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
