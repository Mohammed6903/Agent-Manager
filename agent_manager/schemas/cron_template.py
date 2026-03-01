from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class TemplateVariable(BaseModel):
    key: str
    label: str
    required: bool = True
    default: Optional[str] = None

class CronTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_public: bool = False
    
    required_integrations: List[uuid.UUID] = Field(default_factory=list)
    variables: List[TemplateVariable] = Field(default_factory=list)
    
    schedule_kind: Literal["at", "every", "cron"]
    schedule_expr: str
    schedule_tz: Optional[str] = None
    schedule_human: Optional[str] = None
    
    session_target: Literal["main", "isolated"] = "isolated"
    delivery_mode: Literal["webhook", "none"] = "webhook"
    
    payload_message: str
    pipeline_template: Optional[Dict[str, Any]] = None

class CronTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_public: Optional[bool] = None
    
    required_integrations: Optional[List[uuid.UUID]] = None
    variables: Optional[List[TemplateVariable]] = None
    
    schedule_kind: Optional[Literal["at", "every", "cron"]] = None
    schedule_expr: Optional[str] = None
    schedule_tz: Optional[str] = None
    schedule_human: Optional[str] = None
    
    session_target: Optional[Literal["main", "isolated"]] = None
    delivery_mode: Optional[Literal["webhook", "none"]] = None
    
    payload_message: Optional[str] = None
    pipeline_template: Optional[Dict[str, Any]] = None

class CronTemplateResponse(BaseModel):
    id: str
    created_by_user_id: str
    is_public: bool
    
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    
    required_integrations: List[uuid.UUID]
    variables: List[TemplateVariable]
    
    schedule_kind: str
    schedule_expr: str
    schedule_tz: Optional[str] = None
    schedule_human: Optional[str] = None
    
    session_target: str
    delivery_mode: str
    
    payload_message: str
    pipeline_template: Optional[Dict[str, Any]] = None
    
    created_at: datetime
    updated_at: datetime
    
class CronTemplateInstantiateRequest(BaseModel):
    agent_id: str
    user_id: str
    session_id: str
    variable_values: Dict[str, str] = Field(default_factory=dict)
