"""Google OAuth authentication endpoints."""

import os
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

# TODO: Remove this in production
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from agent_manager.database import get_db
from agent_manager.integrations.google.gmail import auth_service as auth_service
from agent_manager.integrations.google.schemas import ManualCallbackRequest

router = APIRouter()

@router.get("/login", tags=["Google Auth"])
def login(agent_id: str, db: Session = Depends(get_db)):
    scopes = auth_service.get_required_scopes(agent_id, db)
    flow = auth_service.get_google_flow(scopes=scopes, state=agent_id)
    auth_url, _ = flow.authorization_url(prompt="consent")
    return {"auth_url": auth_url}

@router.get("/callback", tags=["Google Auth"])
def callback(request: Request, db: Session = Depends(get_db)):
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="State not found")

    # State is encoded as "agent_id|integration_name" by GoogleOAuth2Flow
    if "|" in state:
        agent_id, integration_name = state.split("|", 1)
    else:
        # Fallback for legacy flows that only have agent_id
        agent_id = state
        integration_name = None

    # Retrieve PKCE code_verifier stored during auth URL generation
    from agent_manager.services.secret_service import SecretService
    pkce_key = f"_google_pkce_{agent_id}"
    code_verifier = None
    try:
        pkce_data = SecretService.get_secret(db, agent_id, pkce_key)
        if pkce_data:
            code_verifier = pkce_data.get("code_verifier")
            SecretService.delete_secret(db, agent_id, pkce_key)
    except Exception:
        pass

    try:
        creds = auth_service.exchange_code_and_store(
            db, agent_id, str(request.url), raw_state=state, code_verifier=code_verifier,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Fetch user profile for metadata (email, name, picture)
    user_metadata = auth_service.fetch_google_user_info(creds) if creds else None

    # OAuth succeeded — assign only the specific requested integration
    from ....repositories.integration_repository import IntegrationRepository
    repo = IntegrationRepository(db)
    if integration_name:
        repo.assign_to_agent(agent_id, integration_name, metadata=user_metadata)
    else:
        # Legacy fallback: assign all Google integrations
        from ... import INTEGRATION_REGISTRY
        from ....integrations.google.base_google import BaseGoogleIntegration
        for name, cls in INTEGRATION_REGISTRY.items():
            if issubclass(cls, BaseGoogleIntegration):
                repo.assign_to_agent(agent_id, name, metadata=user_metadata)

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Authentication Successful</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 8px;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
                text-align: center;
                max-width: 400px;
            }
            .checkmark {
                width: 80px;
                height: 80px;
                margin: 0 auto 20px;
                background: #4CAF50;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 50px;
                color: white;
            }
            h1 {
                color: #333;
                margin: 20px 0 10px 0;
                font-size: 28px;
            }
            p {
                color: #666;
                font-size: 16px;
                line-height: 1.6;
                margin: 10px 0;
            }
            .agent-id {
                background: #f5f5f5;
                padding: 10px;
                border-radius: 4px;
                margin: 20px 0;
                font-family: monospace;
                font-size: 14px;
                color: #333;
                word-break: break-all;
            }
            .instruction {
                color: #999;
                font-size: 14px;
                margin-top: 30px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="checkmark">✓</div>
            <h1>You are Authenticated!</h1>
            <p>Your Google account has been successfully connected.</p>
            <div class="agent-id">Agent ID: """ + agent_id + """</div>
            <p class="instruction">You can now close this window and access your account.</p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.post("/callback/manual", tags=["Google Auth"])
async def manual_callback(body: ManualCallbackRequest, db: Session = Depends(get_db)):
    """Headless OAuth callback — accepts an authorization code or a full redirect URL."""
    if not body.code and not body.redirect_url:
        raise HTTPException(status_code=400, detail="Provide either 'code' or 'redirect_url'")

    try:
        if body.code:
            from ....integrations.auth.oauth2_registry import get_oauth2_provider
            provider = get_oauth2_provider("google")
            await provider.handle_callback(db=db, agent_id=body.agent_id, integration_name="google", code=body.code)
        else:
            auth_service.exchange_code_and_store(db, body.agent_id, body.redirect_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "connected", "agent_id": body.agent_id}
