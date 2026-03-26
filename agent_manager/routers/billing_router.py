"""Billing router — usage and cost data aggregations."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_usage_service, get_subscription_service
from ..services.usage_service import UsageService
from ..services.subscription_service import SubscriptionService
from ..repositories.wallet_transaction_repository import WalletTransactionRepository
from ..repositories.agent_registry_repository import AgentRegistryRepository

router = APIRouter(tags=["Billing"])


@router.get("/billing/transactions")
async def get_transactions(
    user_id: Annotated[str, Query(...)],
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    type: Annotated[Optional[str], Query(description="Filter by type: subscription_initial, subscription_renewal, subscription_unlock, usage_deduction, top_up, refund")] = None,
):
    """Return paginated wallet transactions for a user, with optional type filter."""
    txn_repo = WalletTransactionRepository(db)
    agent_repo = AgentRegistryRepository(db)
    rows = txn_repo.list_by_user(user_id, limit=limit, offset=offset, type_filter=type)

    # Build agent name cache
    agent_ids = {r.agent_id for r in rows if r.agent_id}
    agent_names: dict[str, str] = {}
    for aid in agent_ids:
        agent = agent_repo.get(aid)
        if agent:
            agent_names[aid] = agent.name

    return [
        {
            "id": str(r.id),
            "user_id": r.user_id,
            "agent_id": r.agent_id,
            "agent_name": agent_names.get(r.agent_id) if r.agent_id else None,
            "type": r.type,
            "amount_cents": r.amount_cents,
            "description": r.description,
            "status": r.status,
            "reference_id": r.reference_id,
            "balance_after_cents": r.balance_after_cents,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/billing/usage/agents/monthly-chart")
async def get_agents_monthly_chart(
    user_id: Annotated[str, Query(...)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
    org_id: Annotated[Optional[str], Query()] = None,
):
    return await usage_service.get_agents_monthly_usage_chart(user_id=user_id, org_id=org_id)


@router.get("/billing/usage/agents/summary")
async def get_agents_summary(
    user_id: Annotated[str, Query(...)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
    org_id: Annotated[Optional[str], Query()] = None,
):
    return await usage_service.get_agents_summary(user_id=user_id, org_id=org_id)


@router.get("/billing/usage/models")
async def get_usage_per_model(
    user_id: Annotated[str, Query(...)],
    agent_id: Annotated[Optional[str], Query()] = None,
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
    org_id: Annotated[Optional[str], Query()] = None,
):
    return usage_service.get_usage_per_model(user_id=user_id, agent_id=agent_id, org_id=org_id)


@router.get("/billing/usage/current-month")
async def get_current_month_usage(
    user_id: Annotated[str, Query(...)],
    agent_id: Annotated[Optional[str], Query()] = None,
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
    org_id: Annotated[Optional[str], Query()] = None,
):
    return usage_service.get_current_month_usage(user_id=user_id, agent_id=agent_id, org_id=org_id)


@router.get("/billing/usage/daily-7d")
async def get_daily_usage_last_7_days(
    user_id: Annotated[str, Query(...)],
    agent_id: Annotated[Optional[str], Query()] = None,
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
    org_id: Annotated[Optional[str], Query()] = None,
):
    return usage_service.get_daily_usage_last_7_days(user_id=user_id, agent_id=agent_id, org_id=org_id)


@router.get("/billing/usage/monthly-12m")
async def get_monthly_usage_last_12_months(
    user_id: Annotated[str, Query(...)],
    agent_id: Annotated[Optional[str], Query()] = None,
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
    org_id: Annotated[Optional[str], Query()] = None,
):
    return usage_service.get_monthly_usage_last_12_months(user_id=user_id, agent_id=agent_id, org_id=org_id)


# ── Subscription endpoints ─────────────────────────────────────────────────


@router.get("/billing/subscriptions")
async def list_subscriptions(
    org_id: Annotated[str, Query(...)],
    sub_service: Annotated[SubscriptionService, Depends(get_subscription_service)],
):
    """List all active/locked subscriptions for a workspace."""
    subs = sub_service.list_org_subscriptions(org_id)
    return [
        {
            "agent_id": s.agent_id,
            "org_id": s.org_id,
            "user_id": s.user_id,
            "status": s.status,
            "amount_cents": s.amount_cents,
            "next_billing_date": s.next_billing_date.isoformat() if s.next_billing_date else None,
            "locked_at": s.locked_at.isoformat() if s.locked_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in subs
    ]


@router.get("/billing/subscriptions/{agent_id}")
async def get_subscription(
    agent_id: str,
    sub_service: Annotated[SubscriptionService, Depends(get_subscription_service)],
):
    """Get subscription details for a specific agent."""
    sub = sub_service.get_subscription(agent_id)
    if not sub:
        return {"agent_id": agent_id, "status": "none"}
    return {
        "agent_id": sub.agent_id,
        "org_id": sub.org_id,
        "user_id": sub.user_id,
        "status": sub.status,
        "amount_cents": sub.amount_cents,
        "next_billing_date": sub.next_billing_date.isoformat() if sub.next_billing_date else None,
        "locked_at": sub.locked_at.isoformat() if sub.locked_at else None,
        "deleted_at": sub.deleted_at.isoformat() if sub.deleted_at else None,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


@router.post("/billing/subscriptions/{agent_id}/unlock")
async def unlock_agent(
    agent_id: str,
    user_id: Annotated[str, Query(description="User paying to unlock the agent")],
    sub_service: Annotated[SubscriptionService, Depends(get_subscription_service)],
):
    """Pay $24 to unlock a locked agent and reactivate its subscription."""
    sub = await sub_service.unlock_agent(agent_id, user_id)
    return {
        "status": "unlocked",
        "agent_id": sub.agent_id,
        "next_billing_date": sub.next_billing_date.isoformat() if sub.next_billing_date else None,
    }