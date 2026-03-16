"""Billing router — usage and cost data aggregations."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ..dependencies import get_usage_service
from ..services.usage_service import UsageService

router = APIRouter(tags=["Billing"])


@router.get("/billing/usage/models")
async def get_usage_per_model(
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
):
    """Return aggregated token and cost usage grouped by model across all agents."""
    return usage_service.get_usage_per_model()


@router.get("/billing/usage/current-month")
async def get_current_month_usage(
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
):
    """Return an aggregated overview of the current month's token spend and costs."""
    return usage_service.get_current_month_usage()


@router.get("/billing/usage/daily-7d")
async def get_daily_usage_last_7_days(
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
):
    """Return daily cost and token usage aggregations for the past 7 days."""
    return usage_service.get_daily_usage_last_7_days()


@router.get("/billing/usage/monthly-12m")
async def get_monthly_usage_last_12_months(
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
):
    """Return monthly cost and token usage aggregations for the rolling past 12 months."""
    return usage_service.get_monthly_usage_last_12_months()