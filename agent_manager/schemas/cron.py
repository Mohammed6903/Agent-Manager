from typing import Literal, Optional, List
from pydantic import BaseModel

class CreateCronRequest(BaseModel):
    name: str
    agent_id: str
    schedule_kind: Literal["at", "every", "cron"]
    schedule_expr: str          # ISO timestamp / ms interval / cron expression
    schedule_tz: Optional[str] = None     # IANA timezone, only for kind=cron
    session_target: Literal["main", "isolated"] = "isolated"
    payload_message: str        # the prompt the agent will receive
    delivery_mode: Literal["webhook", "none"] = "webhook"
    enabled: bool = True
    delete_after_run: bool = False
    pipeline_template: Optional[dict] = None
    schedule_human: Optional[str] = None
    # Ownership fields
    user_id: str
    session_id: str

class UpdateCronRequest(BaseModel):
    schedule_kind: Optional[Literal["at", "every", "cron"]] = None
    schedule_expr: Optional[str] = None
    schedule_tz: Optional[str] = None
    payload_message: Optional[str] = None
    enabled: Optional[bool] = None

class CronResponse(BaseModel):
    job_id: str
    name: str
    agent_id: str
    schedule: dict
    payload_message: str
    delivery_mode: str
    enabled: bool
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    last_run_at: Optional[int] = None
    next_run_at: Optional[int] = None
    last_run_status: Optional[str] = None
    description: Optional[str] = None
    schedule_human: Optional[str] = None
    pipeline_template: Optional[dict] = None
    last_run_summary: Optional[str] = None
    total_runs: Optional[int] = None
    success_rate: Optional[float] = None
    avg_duration_ms: Optional[float] = None
