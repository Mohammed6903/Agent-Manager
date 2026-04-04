import logging

from sqlalchemy.orm import Session
from fastapi import HTTPException

from agent_manager.integrations.auth.oauth2_flow import OAuth2FlowProvider
from agent_manager.integrations.google.gmail.auth_service import (
    get_google_flow, get_required_scopes, exchange_code_with_code,
)
from agent_manager.services.secret_service import SecretService

logger = logging.getLogger(__name__)

# Key prefix for storing PKCE code_verifier temporarily
_PKCE_KEY_PREFIX = "_google_pkce_"


class GoogleOAuth2Flow(OAuth2FlowProvider):

    def get_auth_url(self, agent_id: str, integration_name: str, db: Session = None) -> str:
        if db:
            scopes = get_required_scopes(agent_id, db, include_integration=integration_name)
        else:
            from ..schemas import BaseGoogleIntegration
            from ... import INTEGRATION_REGISTRY
            target_cls = INTEGRATION_REGISTRY.get(integration_name)
            if target_cls and issubclass(target_cls, BaseGoogleIntegration):
                scopes = getattr(target_cls, "scopes", ["https://www.googleapis.com/auth/userinfo.email"])
            else:
                scopes = ["https://www.googleapis.com/auth/userinfo.email"]

        composite_state = f"{agent_id}|{integration_name}"
        flow = get_google_flow(scopes=scopes, state=composite_state)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

        # Store the PKCE code_verifier so the callback can use it.
        # google-auth-oauthlib ≥0.8 auto-generates PKCE params.
        code_verifier = flow.code_verifier
        if code_verifier and db:
            SecretService.set_secret(
                db, agent_id,
                f"{_PKCE_KEY_PREFIX}{agent_id}",
                {"code_verifier": code_verifier},
            )

        return auth_url

    async def handle_callback(
        self,
        db: Session,
        agent_id: str,
        integration_name: str,
        code: str,
        **kwargs,
    ) -> dict:
        # Retrieve the stored PKCE code_verifier
        pkce_key = f"{_PKCE_KEY_PREFIX}{agent_id}"
        code_verifier = None
        try:
            pkce_data = SecretService.get_secret(db, agent_id, pkce_key)
            if pkce_data:
                code_verifier = pkce_data.get("code_verifier")
                # Clean up — one-time use
                SecretService.delete_secret(db, agent_id, pkce_key)
        except Exception:
            logger.warning("Failed to retrieve PKCE code_verifier for agent %s", agent_id)

        try:
            creds = exchange_code_with_code(db, agent_id, code, code_verifier=code_verifier)
            if not creds:
                raise HTTPException(status_code=400, detail="Google OAuth exchange returned no credentials")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Google OAuth exchange failed: {str(e)}")

        return {"status": "authorized", "agent_id": agent_id, "integration": integration_name}

