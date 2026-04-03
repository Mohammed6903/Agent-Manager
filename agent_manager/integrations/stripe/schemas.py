"""Pydantic request schemas for Stripe endpoints."""

from typing import Dict, Optional
from pydantic import BaseModel, Field


class StripeAgentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")


class StripeListRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    limit: Optional[int] = Field(None, description="Number of objects to return (max 100).")
    starting_after: Optional[str] = Field(None, description="Cursor for pagination.")


class StripeCustomerIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    customer_id: str = Field(..., description="Customer ID (cus_...).")


class StripeCreateCustomerRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    email: Optional[str] = Field(None, description="Customer email.")
    name: Optional[str] = Field(None, description="Customer name.")
    metadata: Optional[Dict[str, str]] = Field(None, description="Key-value metadata.")


class StripeUpdateCustomerRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    email: Optional[str] = Field(None, description="Updated email.")
    name: Optional[str] = Field(None, description="Updated name.")


class StripeCustomerFilterRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    limit: Optional[int] = Field(None, description="Number of objects to return.")
    customer: Optional[str] = Field(None, description="Filter by customer ID.")


class StripePaymentIntentIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    payment_intent_id: str = Field(..., description="Payment intent ID (pi_...).")


class StripeCreatePaymentIntentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    amount: int = Field(..., description="Amount in smallest currency unit (e.g. cents).")
    currency: str = Field(..., description="Three-letter ISO currency code (e.g. 'usd').")
    customer: Optional[str] = Field(None, description="Customer ID.")


class StripeInvoiceIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    invoice_id: str = Field(..., description="Invoice ID (in_...).")


class StripeCreateInvoiceRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    customer: str = Field(..., description="Customer ID.")
    auto_advance: Optional[bool] = Field(None, description="Auto-finalize the invoice.")


class StripeSubscriptionIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    subscription_id: str = Field(..., description="Subscription ID (sub_...).")


class StripeCreateSubscriptionRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    customer: str = Field(..., description="Customer ID.")
    price: str = Field(..., description="Price ID (price_...).")


class StripeProductIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    product_id: str = Field(..., description="Product ID (prod_...).")


class StripeCreateProductRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    name: str = Field(..., description="Product name.")


class StripeCreatePriceRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Stripe integration assigned.")
    product: str = Field(..., description="Product ID.")
    unit_amount: int = Field(..., description="Price in smallest currency unit.")
    currency: str = Field(..., description="Three-letter ISO currency code.")
    recurring_interval: Optional[str] = Field(None, description="Recurring interval: day, week, month, year.")
