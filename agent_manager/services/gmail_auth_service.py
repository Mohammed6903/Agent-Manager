"""Gmail OAuth authentication service."""

from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from ..models.gmail import GoogleAccount
from ..models.integration import AgentIntegration
from ..security import encrypt, decrypt
from ..config import settings

import os
import json
import datetime
import logging

logger = logging.getLogger(__name__)

# Fallback scopes if an agent has no specific google integrations assigned yet
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

# Identity scopes always included so we can fetch user profile/email for metadata
IDENTITY_SCOPES = {
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
}

# Get the directory of the current file
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# credentials file is in the parent (agent_manager/) directory
CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(CURRENT_DIR), "credentials_for_local.json")

REDIRECT_URI = f"{settings.SERVER_URL}/api/integrations/google/auth/callback"

def get_required_scopes(agent_id: str, db: Session, include_integration: str = None) -> list[str]:
    """Dynamically build requested scopes based on the agent's assigned Google integrations.
    
    Args:
        include_integration: If provided, also include the scopes of this integration
                             even if it's not yet assigned to the agent in the DB.
    """
    agent_integrations = db.query(AgentIntegration).filter(AgentIntegration.agent_id == agent_id).all()
    scopes = set()
    
    from ..integrations import INTEGRATION_REGISTRY
    from ..integrations.google.base_google import BaseGoogleIntegration
    
    for record in agent_integrations:
        integration_cls = INTEGRATION_REGISTRY.get(record.integration_name)
        if integration_cls and issubclass(integration_cls, BaseGoogleIntegration):
            # Union all scopes requested by all Google integrations
            for scope in getattr(integration_cls, "scopes", []):
                scopes.add(scope)

    # Also include the scopes of the integration being assigned right now
    if include_integration:
        target_cls = INTEGRATION_REGISTRY.get(include_integration)
        if target_cls and issubclass(target_cls, BaseGoogleIntegration):
            for scope in getattr(target_cls, "scopes", []):
                scopes.add(scope)
                
    if not scopes:
        return DEFAULT_SCOPES
    # Always include identity scopes so the userinfo endpoint is accessible
    # regardless of which Google integration is being assigned.
    scopes.update(IDENTITY_SCOPES)
    return list(scopes)

def get_google_flow(scopes: list[str], state=None):
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=scopes,
        redirect_uri=REDIRECT_URI,
        state=state,
    )

def exchange_code_and_store(db: Session, agent_id: str, authorization_response: str, raw_state: str = None):
    """Exchange the authorization code for tokens.
    
    Uses the scopes from the callback URL (what Google actually granted)
    rather than re-querying the DB, which may not have the new integration yet.
    
    Args:
        raw_state: The original state from the callback URL. Must match
                   the state used when the auth URL was generated.
    """
    from urllib.parse import urlparse, parse_qs

    # Google sometimes uses shorthand aliases in the callback scope param
    # (e.g. "profile" / "email") when include_granted_scopes=true re-includes
    # previously granted scopes. oauthlib's scope-change check then fails because
    # the token response normalises them to full URIs. Map them upfront.
    _SCOPE_ALIASES = {
        "profile": "https://www.googleapis.com/auth/userinfo.profile",
        "email": "https://www.googleapis.com/auth/userinfo.email",
    }

    # Extract the actual granted scopes from Google's callback URL
    parsed = urlparse(authorization_response)
    qs = parse_qs(parsed.query)
    callback_scopes = qs.get("scope", [])
    
    if callback_scopes:
        # Google returns scopes as a space-separated string in a single list element
        raw_scopes = callback_scopes[0].split()
        scopes = [_SCOPE_ALIASES.get(s, s) for s in raw_scopes]
        # Deduplicate while preserving order (shorthand + full URI can both appear)
        seen = set()
        scopes = [s for s in scopes if not (s in seen or seen.add(s))]
    else:
        # Fallback to DB-based scopes if not in URL
        scopes = get_required_scopes(agent_id, db)
    
    # Use the raw_state (e.g. "agent_id|integration_name") so it matches
    # what Google returns in the callback — prevents CSRF mismatch.
    flow_state = raw_state if raw_state else agent_id
    flow = get_google_flow(scopes=scopes, state=flow_state)
    flow.fetch_token(authorization_response=authorization_response)
    credentials = flow.credentials
    store_credentials(db, agent_id, credentials)
    return credentials


def exchange_code_with_code(db: Session, agent_id: str, code: str):
    """Exchange a raw authorization code for tokens (headless flow)."""
    scopes = get_required_scopes(agent_id, db)
    flow = get_google_flow(scopes=scopes, state=agent_id)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    store_credentials(db, agent_id, credentials)
    return credentials


def store_credentials(db: Session, agent_id: str, credentials):
    access_token = credentials.token
    refresh_token = credentials.refresh_token
    # Ensure expiry is always timezone-aware UTC for TIMESTAMPTZ column
    expiry = credentials.expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=datetime.timezone.utc)

    encrypted_access = encrypt(access_token)
    encrypted_refresh = encrypt(refresh_token) if refresh_token else None

    account = db.query(GoogleAccount).filter(GoogleAccount.agent_id == agent_id).first()
    if not account:
        account = GoogleAccount(
            agent_id=agent_id,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            expiry=expiry
        )
        db.add(account)
    else:
        account.access_token = encrypted_access
        if refresh_token: # Only update refresh token if present (sometimes it's not returned on refresh)
            account.refresh_token = encrypted_refresh
        account.expiry = expiry

    db.commit()
    db.refresh(account)
    return account

def get_valid_credentials(db: Session, agent_id: str):
    account = db.query(GoogleAccount).filter(GoogleAccount.agent_id == agent_id).first()
    if not account:
        logger.warning(f"No account found for agent_id={agent_id}")
        return None

    access_token = decrypt(account.access_token)
    refresh_token = decrypt(account.refresh_token) if account.refresh_token else None

    # Check expiry ourselves to avoid timezone mismatch inside google-auth.
    # We normalise both sides to naive UTC before comparing.
    expiry = account.expiry
    is_expired = False
    if expiry is not None:
        expiry_naive = expiry.replace(tzinfo=None) if expiry.tzinfo else expiry
        now_naive = datetime.datetime.utcnow()
        is_expired = now_naive >= expiry_naive

    if is_expired and refresh_token:
        # Token expired — build creds with refresh_token and refresh immediately
        logger.info(f"Access token expired for agent_id={agent_id}, refreshing...")
        scopes = get_required_scopes(agent_id, db)
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=get_client_id_from_file(),
            client_secret=get_client_secret_from_file(),
            scopes=scopes,
        )
        try:
            creds.refresh(Request())
            store_credentials(db, agent_id, creds)
            logger.info(f"Token refreshed successfully for agent_id={agent_id}")
        except Exception as e:
            logger.error(f"Token refresh failed for agent_id={agent_id}: {e}", exc_info=True)
            return None
        return creds

    elif is_expired and not refresh_token:
        logger.error(f"Access token expired for agent_id={agent_id} but no refresh token — re-auth required")
        return None

    # Token still valid — do NOT pass expiry to avoid any timezone comparison
    # inside google-auth or googleapiclient transport layer.
    scopes = get_required_scopes(agent_id, db)
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=get_client_id_from_file(),
        client_secret=get_client_secret_from_file(),
        scopes=scopes,
    )
    return creds

def get_client_id_from_file():
    with open(CLIENT_SECRETS_FILE, 'r') as f:
        data = json.load(f)
        return data['web']['client_id']

def get_client_secret_from_file():
    with open(CLIENT_SECRETS_FILE, 'r') as f:
        data = json.load(f)
        return data['web']['client_secret']

def fetch_google_user_info(credentials) -> dict:
    """Fetch basic profile info from Google's userinfo endpoint using the provided credentials.
    
    Returns a dict with 'email', 'name', and optionally 'picture'.
    Returns an empty dict on failure so callers can treat it as optional metadata.
    """
    import requests
    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {k: v for k, v in {
                "email": data.get("email"),
                "name": data.get("name"),
                "picture": data.get("picture"),
            }.items() if v is not None}
    except Exception as e:
        logger.warning(f"Failed to fetch Google user info: {e}")
    return {}
