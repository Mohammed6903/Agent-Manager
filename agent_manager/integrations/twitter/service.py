"""Twitter operations service."""

import logging
import time
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
import httpx

from agent_manager.services.secret_service import SecretService
from agent_manager.integrations.sdk_logger import log_integration_call
from agent_manager.config import settings
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

async def _refresh_twitter_token(db: Session, agent_id: str, refresh_token: str) -> dict:
    """Refresh the Twitter OAuth 2.0 token."""
    token_url = "https://api.twitter.com/2/oauth2/token"
    auth = (str(settings.TWITTER_CLIENT_ID), str(settings.TWITTER_CLIENT_SECRET))
    
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": str(settings.TWITTER_CLIENT_ID)
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=payload, auth=auth, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Failed to refresh Twitter token for agent {agent_id}: {resp.text}")
            raise Exception("Failed to refresh Twitter token")
        
        tokens = resp.json()
        if "expires_in" in tokens:
            tokens["expires_at"] = int(time.time()) + int(tokens["expires_in"])
        
        # Store updated tokens
        string_tokens = {k: str(v) for k, v in tokens.items() if v is not None}
        SecretService.set_secret(db, agent_id, "twitter", string_tokens)
        return tokens

@asynccontextmanager
async def _get_twitter_client(db: Session, agent_id: str):
    creds = SecretService.get_secret(db, agent_id, "twitter")
    if not creds:
        raise Exception("Twitter credentials not found for agent")
    
    access_token = creds.get("access_token")
    refresh_token = creds.get("refresh_token")
    expires_at = creds.get("expires_at")

    should_refresh = False
    if expires_at and int(time.time()) + 60 > int(expires_at):
        should_refresh = True
    elif not expires_at and refresh_token:
        should_refresh = True

    if should_refresh and refresh_token:
        try:
            logger.info(f"Refreshing Twitter token for agent {agent_id}")
            new_tokens = await _refresh_twitter_token(db, agent_id, refresh_token)
            access_token = new_tokens.get("access_token")
        except Exception as e:
            logger.warning(f"Could not refresh Twitter token: {e}. Attempting with current token.")

    if not access_token:
        raise Exception("Twitter access token not found")
        
    async with httpx.AsyncClient(
        base_url="https://api.twitter.com/2",
        headers={"Authorization": f"Bearer {access_token}"}
    ) as client:
        yield client


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
