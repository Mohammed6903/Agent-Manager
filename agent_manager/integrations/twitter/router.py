"""Twitter endpoints router."""


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_manager.database import get_db
from agent_manager.integrations.twitter.schemas import CreateTweetRequest, SendDMRequest

router = APIRouter()

@router.post("/tweets", tags=["Twitter / X"])
async def create_tweet(body: CreateTweetRequest, db: Session = Depends(get_db)):
    """Create a new tweet on behalf of the authenticated user."""
    try:
        result = await twitter_service.create_tweet(db, body.agent_id, body.text)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tweets/{tweet_id}", tags=["Twitter / X"])
async def delete_tweet(agent_id: str, tweet_id: str, db: Session = Depends(get_db)):
    """Delete a specific tweet by ID."""
    try:
        result = await twitter_service.delete_tweet(db, agent_id, tweet_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/me", tags=["Twitter / X"])
async def get_my_profile(agent_id: str, db: Session = Depends(get_db)):
    """Get the authenticated user's profile details."""
    try:
        result = await twitter_service.get_users_me(db, agent_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}", tags=["Twitter / X"])
async def get_user_by_id(agent_id: str, user_id: str, db: Session = Depends(get_db)):
    """Get a user's details by their Twitter user ID."""
    try:
        result = await twitter_service.get_user_by_id(db, agent_id, user_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/by/username/{username}", tags=["Twitter / X"])
async def get_user_by_username(agent_id: str, username: str, db: Session = Depends(get_db)):
    """Get a user's details by their Twitter handle (username)."""
    try:
        result = await twitter_service.get_user_by_username(db, agent_id, username)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}/tweets", tags=["Twitter / X"])
async def get_user_recent_tweets(agent_id: str, user_id: str, max_results: int = 10, db: Session = Depends(get_db)):
    """Get recent tweets posted by a specific user ID."""
    try:
        result = await twitter_service.get_user_tweets(db, agent_id, user_id, max_results)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}/mentions", tags=["Twitter / X"])
async def get_user_mentions(agent_id: str, user_id: str, max_results: int = 10, db: Session = Depends(get_db)):
    """Get recent mentions for a specific user ID."""
    try:
        result = await twitter_service.get_user_mentions(db, agent_id, user_id, max_results)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tweets/search/recent", tags=["Twitter / X"])
async def search_recent_tweets(agent_id: str, query: str, max_results: int = 10, db: Session = Depends(get_db)):
    """Search for recent tweets matching a specific query."""
    try:
        result = await twitter_service.search_recent_tweets(db, agent_id, query, max_results)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}/followers", tags=["Twitter / X"])
async def get_followers(agent_id: str, user_id: str, max_results: int = 10, db: Session = Depends(get_db)):
    """Get a list of followers for a specific user ID."""
    try:
        result = await twitter_service.get_user_followers(db, agent_id, user_id, max_results)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}/following", tags=["Twitter / X"])
async def get_following(agent_id: str, user_id: str, max_results: int = 10, db: Session = Depends(get_db)):
    """Get a list of users that a specific user ID is following."""
    try:
        result = await twitter_service.get_user_following(db, agent_id, user_id, max_results)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dm_conversations/with/{participant_id}/dm_events", tags=["Twitter / X"])
async def get_dm_history(agent_id: str, participant_id: str, max_results: int = 10, db: Session = Depends(get_db)):
    """Get direct message history with a specific participant ID."""
    try:
        result = await twitter_service.get_dm_events(db, agent_id, participant_id, max_results)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dm_conversations/with/{participant_id}/messages", tags=["Twitter / X"])
async def send_direct_message(participant_id: str, body: SendDMRequest, db: Session = Depends(get_db)):
    """Send a direct message to a specific participant ID."""
    try:
        result = await twitter_service.send_dm(db, body.agent_id, participant_id, body.text)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
