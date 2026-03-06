"""Google OAuth authentication endpoints."""

import os
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

# TODO: Remove this in production
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from ..database import get_db
from ..services import gmail_auth_service as auth_service
from ..schemas.gmail import ManualCallbackRequest

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

    try:
        auth_service.exchange_code_and_store(db, state, str(request.url))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
            <div class="agent-id">Agent ID: """ + state + """</div>
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
            from ..integrations.auth.oauth2_registry import get_oauth2_provider
            provider = get_oauth2_provider("google")
            await provider.handle_callback(db=db, agent_id=body.agent_id, integration_name="google", code=body.code)
        else:
            auth_service.exchange_code_and_store(db, body.agent_id, body.redirect_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "connected", "agent_id": body.agent_id}
