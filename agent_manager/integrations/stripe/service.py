"""Stripe operations service.

Note: Stripe uses application/x-www-form-urlencoded for POST bodies,
so we use `data=` instead of `json=` for write operations.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ...services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "stripe"


async def _get_client(db: Session, agent_id: str):
    svc = IntegrationService(db)
    return svc.get_client(agent_id, INTEGRATION_NAME)


# Balance
async def get_balance(db: Session, agent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/balance")
        resp.raise_for_status()
        return resp.json()


# Customers
async def list_customers(db: Session, agent_id: str, limit: Optional[int] = None, starting_after: Optional[str] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if starting_after is not None:
        params["starting_after"] = starting_after
    async with client:
        resp = await client.get(f"{client.base_url}/customers", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_customer(db: Session, agent_id: str, customer_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/customers/{customer_id}")
        resp.raise_for_status()
        return resp.json()


async def create_customer(db: Session, agent_id: str, email: Optional[str] = None, name: Optional[str] = None, metadata: Optional[Dict[str, str]] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if email is not None:
        payload["email"] = email
    if name is not None:
        payload["name"] = name
    if metadata is not None:
        for k, v in metadata.items():
            payload[f"metadata[{k}]"] = v
    async with client:
        resp = await client.post(f"{client.base_url}/customers", data=payload)
        resp.raise_for_status()
        return resp.json()


async def update_customer(db: Session, agent_id: str, customer_id: str, email: Optional[str] = None, name: Optional[str] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {}
    if email is not None:
        payload["email"] = email
    if name is not None:
        payload["name"] = name
    async with client:
        resp = await client.post(f"{client.base_url}/customers/{customer_id}", data=payload)
        resp.raise_for_status()
        return resp.json()


# Payment Intents
async def list_payment_intents(db: Session, agent_id: str, limit: Optional[int] = None, customer: Optional[str] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if customer is not None:
        params["customer"] = customer
    async with client:
        resp = await client.get(f"{client.base_url}/payment_intents", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_payment_intent(db: Session, agent_id: str, payment_intent_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/payment_intents/{payment_intent_id}")
        resp.raise_for_status()
        return resp.json()


async def create_payment_intent(db: Session, agent_id: str, amount: int, currency: str, customer: Optional[str] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"amount": amount, "currency": currency}
    if customer is not None:
        payload["customer"] = customer
    async with client:
        resp = await client.post(f"{client.base_url}/payment_intents", data=payload)
        resp.raise_for_status()
        return resp.json()


# Invoices
async def list_invoices(db: Session, agent_id: str, limit: Optional[int] = None, customer: Optional[str] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if customer is not None:
        params["customer"] = customer
    async with client:
        resp = await client.get(f"{client.base_url}/invoices", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_invoice(db: Session, agent_id: str, invoice_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/invoices/{invoice_id}")
        resp.raise_for_status()
        return resp.json()


async def create_invoice(db: Session, agent_id: str, customer: str, auto_advance: Optional[bool] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"customer": customer}
    if auto_advance is not None:
        payload["auto_advance"] = str(auto_advance).lower()
    async with client:
        resp = await client.post(f"{client.base_url}/invoices", data=payload)
        resp.raise_for_status()
        return resp.json()


# Subscriptions
async def list_subscriptions(db: Session, agent_id: str, limit: Optional[int] = None, customer: Optional[str] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if customer is not None:
        params["customer"] = customer
    async with client:
        resp = await client.get(f"{client.base_url}/subscriptions", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_subscription(db: Session, agent_id: str, subscription_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/subscriptions/{subscription_id}")
        resp.raise_for_status()
        return resp.json()


async def create_subscription(db: Session, agent_id: str, customer: str, price: str):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"customer": customer, "items[0][price]": price}
    async with client:
        resp = await client.post(f"{client.base_url}/subscriptions", data=payload)
        resp.raise_for_status()
        return resp.json()


async def cancel_subscription(db: Session, agent_id: str, subscription_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.delete(f"{client.base_url}/subscriptions/{subscription_id}")
        resp.raise_for_status()
        return resp.json()


# Products
async def list_products(db: Session, agent_id: str, limit: Optional[int] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    async with client:
        resp = await client.get(f"{client.base_url}/products", params=params)
        resp.raise_for_status()
        return resp.json()


async def get_product(db: Session, agent_id: str, product_id: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.get(f"{client.base_url}/products/{product_id}")
        resp.raise_for_status()
        return resp.json()


async def create_product(db: Session, agent_id: str, name: str):
    client = await _get_client(db, agent_id)
    async with client:
        resp = await client.post(f"{client.base_url}/products", data={"name": name})
        resp.raise_for_status()
        return resp.json()


# Prices
async def list_prices(db: Session, agent_id: str, limit: Optional[int] = None, product: Optional[str] = None):
    client = await _get_client(db, agent_id)
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if product is not None:
        params["product"] = product
    async with client:
        resp = await client.get(f"{client.base_url}/prices", params=params)
        resp.raise_for_status()
        return resp.json()


async def create_price(db: Session, agent_id: str, product: str, unit_amount: int, currency: str, recurring_interval: Optional[str] = None):
    client = await _get_client(db, agent_id)
    payload: Dict[str, Any] = {"product": product, "unit_amount": unit_amount, "currency": currency}
    if recurring_interval is not None:
        payload["recurring[interval]"] = recurring_interval
    async with client:
        resp = await client.post(f"{client.base_url}/prices", data=payload)
        resp.raise_for_status()
        return resp.json()
