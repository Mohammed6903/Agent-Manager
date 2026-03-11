import logging

from sqlalchemy.orm import Session
from fastapi import HTTPException, Request

from .oauth2_flow import OAuth2FlowProvider
from ...services.secret_service import SecretService
from ...services.twitter_auth_service import get_request_token, exchange_verifier

logger = logging.getLogger(__name__)


# We still subclass OAuth2FlowProvider to fit into the generic callback router seamlessly.
# The interface (get_auth_url, handle_callback) is generic enough for OAuth 1.0a 3-legged flow.
class TwitterOAuth1Flow(OAuth2FlowProvider):
    """OAuth 1.0a 3-legged flow for Twitter / X."""
    
    # We use sync wrapper here since the repository methods are sync, 
    # but the flow provider interface expects synchronous get_auth_url.
    # To handle the async get_request_token, we'll need a slight tweak to how auth_url is fetched,
    # or we can use an event loop. Wait, the actual IntegrationRepository calling get_auth_url is sync.
    # Let me use asyncio.run or similar.
    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        import asyncio
        composite_state = f"{agent_id}|{integration_name}"
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we are already in an event loop (e.g. FastAPI request), we shouldn't use asyncio.run
                # Wait, the repository is called from a sync context currently? No, FastAPI endpoints are async.
                # Let's adjust this to be safe.
                import threading
                def _run_coro(coro):
                    res = []
                    ex = []
                    def _thread_target():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            res.append(loop.run_until_complete(coro))
                        except Exception as e:
                            ex.append(e)
                        finally:
                            loop.close()
                    t = threading.Thread(target=_thread_target)
                    t.start()
                    t.join()
                    if ex:
                        raise ex[0]
                    return res[0]
                auth_url, req_token, req_secret = _run_coro(get_request_token(state=composite_state))
            else:
                auth_url, req_token, req_secret = asyncio.run(get_request_token(state=composite_state))
        except Exception as e:
            logger.error(f"Failed to get Twitter request token: {e}")
            raise HTTPException(status_code=500, detail="Failed to initialize Twitter Auth. Check API keys.")

        if db:
            SecretService.set_secret(
                db, 
                agent_id, 
                f"_twitter_oauth1_{agent_id}", 
                {"request_token": req_token, "request_token_secret": req_secret}
            )
        
        return auth_url

    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str, # For OAuth 1.0a, this 'code' parameter in the router will be None!
        request: Request = None, # We need the raw request to extract oauth_verifier
    ) -> dict:
        if not request:
            raise HTTPException(status_code=400, detail="Missing request object in OAuth callback")
        
        # 1. Extract params from the request query string
        oauth_token = request.query_params.get("oauth_token")
        oauth_verifier = request.query_params.get("oauth_verifier")
        denied = request.query_params.get("denied")

        if denied:
            logger.info(f"User denied Twitter Auth for agent {agent_id}")
            raise HTTPException(status_code=400, detail="User denied Twitter authorization")

        if not oauth_token or not oauth_verifier:
            logger.error(f"Missing OAuth 1.0a params. Got token={oauth_token}, verifier={'exists' if oauth_verifier else 'None'}")
            raise HTTPException(status_code=400, detail="Missing required Twitter OAuth callback parameters")

        # 2. Retrieve the request_token_secret from the DB
        temp_secret_name = f"_twitter_oauth1_{agent_id}"
        temp_creds = SecretService.get_secret(db, agent_id, temp_secret_name)
        
        if not temp_creds:
            logger.error(f"Could not find temporary OAuth 1.0 request token for agent {agent_id}")
            raise HTTPException(status_code=400, detail="Twitter auth session expired or invalid. Please try again.")

        request_token_secret = temp_creds.get("request_token_secret")
        if not request_token_secret:
            raise HTTPException(status_code=400, detail="Stored Twitter auth session corrupted")

        # Check that the token matches what we sent
        if temp_creds.get("request_token") != oauth_token:
            logger.error("OAuth token from Twitter does not match the stored request token.")
            raise HTTPException(status_code=400, detail="Twitter OAuth token mismatch")

        # 3. Exchange verifier for access tokens
        try:
            tokens = await exchange_verifier(
                request_token=oauth_token,
                request_token_secret=request_token_secret,
                oauth_verifier=oauth_verifier
            )
        except Exception as e:
            logger.error(f"Failed to exchange Twitter OAuth verifier: {e}")
            raise HTTPException(status_code=400, detail="Failed to get Twitter access token")

        # 4. Store final tokens for the integration
        SecretService.set_secret(db, agent_id, integration_name, tokens)

        # 5. Clean up temporary request tokens
        SecretService.delete_secret(db, agent_id, temp_secret_name)

        return {
            "status": "authorized", 
            "agent_id": agent_id, 
            "integration": integration_name,
            "metadata": {
                "user_id": tokens.get("user_id"),
                "screen_name": tokens.get("screen_name")
            }
        }
