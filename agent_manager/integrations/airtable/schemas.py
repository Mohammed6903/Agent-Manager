"""Pydantic request schemas for Airtable endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AirtableAgentRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Airtable integration assigned.")


class AirtableBaseRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Airtable integration assigned.")
    base_id: str = Field(..., description="Airtable base ID (app...).")


class AirtableListRecordsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Airtable integration assigned.")
    base_id: str = Field(..., description="Airtable base ID.")
    table_id_or_name: str = Field(..., description="Table ID or name.")
    max_records: Optional[int] = Field(None, description="Maximum number of records to return.")
    view: Optional[str] = Field(None, description="View name or ID to filter by.")
    filter_by_formula: Optional[str] = Field(None, description="Airtable formula to filter records.")
    offset: Optional[str] = Field(None, description="Pagination offset from previous response.")


class AirtableGetRecordRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Airtable integration assigned.")
    base_id: str = Field(..., description="Airtable base ID.")
    table_id_or_name: str = Field(..., description="Table ID or name.")
    record_id: str = Field(..., description="Record ID (rec...).")


class AirtableCreateRecordsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Airtable integration assigned.")
    base_id: str = Field(..., description="Airtable base ID.")
    table_id_or_name: str = Field(..., description="Table ID or name.")
    records: List[Dict[str, Any]] = Field(..., description="Array of record objects with 'fields' key.")


class AirtableUpdateRecordsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Airtable integration assigned.")
    base_id: str = Field(..., description="Airtable base ID.")
    table_id_or_name: str = Field(..., description="Table ID or name.")
    records: List[Dict[str, Any]] = Field(..., description="Array of records with 'id' and 'fields' keys.")


class AirtableDeleteRecordsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Airtable integration assigned.")
    base_id: str = Field(..., description="Airtable base ID.")
    table_id_or_name: str = Field(..., description="Table ID or name.")
    record_ids: List[str] = Field(..., description="Array of record IDs to delete.")
