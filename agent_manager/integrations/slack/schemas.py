"""Pydantic request schemas for Slack endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SlackListChannelsRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    types: Optional[str] = Field(None, description="Comma-separated list of channel types: public_channel, private_channel, mpim, im.")
    limit: Optional[int] = Field(None, description="Maximum number of channels to return.")
    cursor: Optional[str] = Field(None, description="Pagination cursor.")


class SlackChannelRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    channel: str = Field(..., description="Channel ID.")


class SlackCreateChannelRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    name: str = Field(..., description="Name of the channel to create.")
    is_private: Optional[bool] = Field(None, description="Whether the channel should be private.")


class SlackChannelHistoryRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    channel: str = Field(..., description="Channel ID.")
    limit: Optional[int] = Field(None, description="Number of messages to return (max 1000).")
    oldest: Optional[str] = Field(None, description="Start of time range (Unix timestamp).")
    latest: Optional[str] = Field(None, description="End of time range (Unix timestamp).")
    cursor: Optional[str] = Field(None, description="Pagination cursor.")


class SlackPostMessageRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    channel: str = Field(..., description="Channel ID to send message to.")
    text: Optional[str] = Field(None, description="Message text (supports mrkdwn).")
    blocks: Optional[List[Dict[str, Any]]] = Field(None, description="Block Kit blocks array.")
    thread_ts: Optional[str] = Field(None, description="Timestamp of parent message for threading.")


class SlackUpdateMessageRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    channel: str = Field(..., description="Channel containing the message.")
    ts: str = Field(..., description="Timestamp of the message to update.")
    text: Optional[str] = Field(None, description="Updated message text.")
    blocks: Optional[List[Dict[str, Any]]] = Field(None, description="Updated Block Kit blocks.")


class SlackDeleteMessageRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    channel: str = Field(..., description="Channel containing the message.")
    ts: str = Field(..., description="Timestamp of the message to delete.")


class SlackReactionRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    channel: str = Field(..., description="Channel where the message is.")
    timestamp: str = Field(..., description="Timestamp of the message.")
    name: str = Field(..., description="Reaction emoji name (without colons).")


class SlackListFilesRequest(BaseModel):
    agent_id: str = Field(..., description="The agent that has the Slack integration assigned.")
    channel: Optional[str] = Field(None, description="Filter files by channel ID.")
    count: Optional[int] = Field(None, description="Number of items to return per page.")
    page: Optional[int] = Field(None, description="Page number of results.")
