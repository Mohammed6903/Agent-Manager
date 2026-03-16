"""Analytics router — per-agent analytics dashboard data."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_analytics_service
from ..schemas.analytics import AgentAnalyticsResponse
from ..services.analytics_service import AnalyticsService

router = APIRouter(tags=["Analytics"])


@router.get(
    "/analytics/agent/{agent_id}",
    response_model=AgentAnalyticsResponse,
)
async def get_agent_analytics(
    agent_id: str,
    user_id: Annotated[str, Query(...)],
    analytics_service: Annotated[AnalyticsService, Depends(get_analytics_service)],
):
    """Return aggregated analytics for a single agent.

    Covers tasks, cron jobs, work time, uptime, token consumption,
    compute/storage, and interaction metrics.
    """
    return await analytics_service.get_agent_analytics(user_id=user_id, agent_id=agent_id)

