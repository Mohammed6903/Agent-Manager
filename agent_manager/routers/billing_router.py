"""Billing router — usage and cost data aggregations."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_usage_service
from ..services.usage_service import UsageService

router = APIRouter(tags=["Billing"])


@router.get("/billing/usage/agents/monthly-chart")
async def get_agents_monthly_chart(
    user_id: Annotated[str, Query(...)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
):
    """Return 12-month token and cost usage grouped by month and agent_id."""
    return await usage_service.get_agents_monthly_usage_chart(user_id=user_id)


@router.get("/billing/usage/agents/summary")
async def get_agents_summary(
    user_id: Annotated[str, Query(...)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
):
    """Return a lifetime and current month usage summary for all agents of a user."""
    return await usage_service.get_agents_summary(user_id=user_id)


@router.get("/billing/usage/models")
async def get_usage_per_model(
    user_id: Annotated[str, Query(...)],
    agent_id: Annotated[Optional[str], Query()] = None,
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
):
    """Return aggregated token and cost usage grouped by model across all agents."""
    return usage_service.get_usage_per_model(user_id=user_id, agent_id=agent_id)


@router.get("/billing/usage/current-month")
async def get_current_month_usage(
    user_id: Annotated[str, Query(...)],
    agent_id: Annotated[Optional[str], Query()] = None,
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
):
    """Return an aggregated overview of the current month's token spend and costs."""
    return usage_service.get_current_month_usage(user_id=user_id, agent_id=agent_id)


@router.get("/billing/usage/daily-7d")
async def get_daily_usage_last_7_days(
    user_id: Annotated[str, Query(...)],
    agent_id: Annotated[Optional[str], Query()] = None,
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
):
    """Return daily cost and token usage aggregations for the past 7 days."""
    return usage_service.get_daily_usage_last_7_days(user_id=user_id, agent_id=agent_id)


@router.get("/billing/usage/monthly-12m")
async def get_monthly_usage_last_12_months(
    user_id: Annotated[str, Query(...)],
    agent_id: Annotated[Optional[str], Query()] = None,
    usage_service: Annotated[UsageService, Depends(get_usage_service)] = None,
):
    """Return monthly cost and token usage aggregations for the rolling past 12 months."""
    return usage_service.get_monthly_usage_last_12_months(user_id=user_id, agent_id=agent_id)