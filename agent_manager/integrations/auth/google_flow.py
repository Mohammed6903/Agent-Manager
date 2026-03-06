from sqlalchemy.orm import Session
from fastapi import HTTPException
from .oauth2_flow import OAuth2FlowProvider
from ...services.gmail_auth_service import get_google_flow, get_required_scopes, exchange_code_with_code

class GoogleOAuth2Flow(OAuth2FlowProvider):
    
    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        if db:
            # include_integration ensures the scopes of the integration being assigned
            # are included even though it's not yet in the DB.
            scopes = get_required_scopes(agent_id, db, include_integration=integration_name)
        else:
            from ..google.base_google import BaseGoogleIntegration
            from .. import INTEGRATION_REGISTRY
            target_cls = INTEGRATION_REGISTRY.get(integration_name)
            if target_cls and issubclass(target_cls, BaseGoogleIntegration):
                scopes = getattr(target_cls, "scopes", ["https://www.googleapis.com/auth/userinfo.email"])
            else:
                scopes = ["https://www.googleapis.com/auth/userinfo.email"]

        flow = get_google_flow(scopes=scopes, state=agent_id)
        auth_url, _ = flow.authorization_url(
            access_type="offline", 
            include_granted_scopes="true", 
            prompt="consent"
        )
        return auth_url

    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str,
    ) -> dict:
        try:
            creds = exchange_code_with_code(db, agent_id, code)
            if not creds:
                raise HTTPException(status_code=400, detail="Google OAuth exchange returned no credentials")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Google OAuth exchange failed: {str(e)}")
            
        return {"status": "authorized", "agent_id": agent_id, "integration": integration_name}
