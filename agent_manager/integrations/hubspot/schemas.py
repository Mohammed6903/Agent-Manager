"""Pydantic request schemas for HubSpot endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HubSpotListRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the HubSpot integration assigned.")
    limit: Optional[int] = Field(None, description="Number of results (max 100).")
    after: Optional[str] = Field(None, description="Pagination cursor.")


class HubSpotObjectIdRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the HubSpot integration assigned.")
    object_id: str = Field(..., description="CRM object ID.")


class HubSpotCreateObjectRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the HubSpot integration assigned.")
    properties: Dict[str, Any] = Field(..., description="Object properties, e.g. {'email': '...', 'firstname': '...'}.")


class HubSpotUpdateObjectRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the HubSpot integration assigned.")
    properties: Dict[str, Any] = Field(..., description="Properties to update.")


class HubSpotSearchRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the HubSpot integration assigned.")
    filter_groups: Optional[List[Dict[str, Any]]] = Field(None, description="Filter groups array.")
    sorts: Optional[List[Dict[str, Any]]] = Field(None, description="Sort criteria.")
    query: Optional[str] = Field(None, description="Search query string.")
    limit: Optional[int] = Field(None, description="Number of results.")
    after: Optional[str] = Field(None, description="Pagination cursor.")
