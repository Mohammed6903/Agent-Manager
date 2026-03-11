"""Twitter operations service."""

import logging
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
import httpx

from .secret_service import SecretService
from ..integrations.sdk_logger import log_integration_call

logger = logging.getLogger(__name__)

def _get_twitter_client(db: Session, agent_id: str) -> httpx.AsyncClient:
    """Helper to get an authenticated HTTP client for Twitter API v2."""
    creds = SecretService.get_secret(db, agent_id, "twitter")
    if not creds:
        raise Exception("Twitter credentials not found for agent")
    
    access_token = creds.get("access_token")
    if not access_token:
        raise Exception("Twitter access token not found in stored credentials")
        
    return httpx.AsyncClient(
        base_url="https://api.twitter.com/2",
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )


@log_integration_call("twitter", "POST", "/tweets")
async def create_tweet(db: Session, agent_id: str, text: str):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.post("/tweets", json={"text": text})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "DELETE", "/tweets/{id}")
async def delete_tweet(db: Session, agent_id: str, tweet_id: str):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.delete(f"/tweets/{tweet_id}")
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/users/me")
async def get_users_me(db: Session, agent_id: str):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.get("/users/me")
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/users/{id}")
async def get_user_by_id(db: Session, agent_id: str, user_id: str):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.get(f"/users/{user_id}")
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/users/by/username/{username}")
async def get_user_by_username(db: Session, agent_id: str, username: str):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.get(f"/users/by/username/{username}")
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/users/{id}/tweets")
async def get_user_tweets(db: Session, agent_id: str, user_id: str, max_results: int = 10):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.get(f"/users/{user_id}/tweets", params={"max_results": max_results})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/users/{id}/mentions")
async def get_user_mentions(db: Session, agent_id: str, user_id: str, max_results: int = 10):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.get(f"/users/{user_id}/mentions", params={"max_results": max_results})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/tweets/search/recent")
async def search_recent_tweets(db: Session, agent_id: str, query: str, max_results: int = 10):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.get("/tweets/search/recent", params={"query": query, "max_results": max_results})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/users/{id}/followers")
async def get_user_followers(db: Session, agent_id: str, user_id: str, max_results: int = 10):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.get(f"/users/{user_id}/followers", params={"max_results": max_results})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/users/{id}/following")
async def get_user_following(db: Session, agent_id: str, user_id: str, max_results: int = 10):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.get(f"/users/{user_id}/following", params={"max_results": max_results})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "GET", "/dm_conversations/with/{participant_id}/dm_events")
async def get_dm_events(db: Session, agent_id: str, participant_id: str, max_results: int = 10):
    async with _get_twitter_client(db, agent_id) as client:
        # Note: DM endpoints typically require OAuth 2.0 or 1.0a User context with specific permissions
        resp = await client.get(f"/dm_conversations/with/{participant_id}/dm_events", params={"max_results": max_results})
        resp.raise_for_status()
        return resp.json()

@log_integration_call("twitter", "POST", "/dm_conversations/with/{participant_id}/messages")
async def send_dm(db: Session, agent_id: str, participant_id: str, text: str):
    async with _get_twitter_client(db, agent_id) as client:
        resp = await client.post(f"/dm_conversations/with/{participant_id}/messages", json={"message": {"text": text}})
        resp.raise_for_status()
        return resp.json()
