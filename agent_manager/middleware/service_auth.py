"""Shared-secret service-to-service auth for OpenClawApi.

Every request outside the public allowlist must carry
`Authorization: Bearer <OPENCLAW_SERVICE_SECRET>`. The only legitimate
caller is roam-backend, which also forwards the end-user identity via
`x-user-id`, `x-org-id`, `x-user-role` headers. Those headers are only
trusted *because* the shared secret validated.

The public allowlist covers paths that external clients reach directly
and therefore cannot carry the service secret:

- Health + OpenAPI docs
- Public Q&A pages (unauthenticated visitors)
- Telnyx webhooks + media-stream WebSocket (signature-verified)
- OAuth callbacks (provider redirects user's browser here)

If `OPENCLAW_SERVICE_SECRET` is empty the middleware is a no-op — lets
us ship the code before flipping enforcement on.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from ..config import settings

logger = logging.getLogger(__name__)

# Path prefixes that bypass the service-auth check.
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/api/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/public/qa",
    "/api/voice/webhooks",
    "/api/voice/stream",
    # Generic OAuth callback router: /api/integrations/oauth/callback/<provider>
    "/api/integrations/oauth/callback",
    # Google-specific auth router mounts its callback here.
    "/api/integrations/google/auth/callback",
)


def _is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def _valid_secrets() -> list[str]:
    secrets = []
    if settings.OPENCLAW_SERVICE_SECRET:
        secrets.append(settings.OPENCLAW_SERVICE_SECRET)
    if settings.OPENCLAW_SERVICE_SECRET_PREVIOUS:
        secrets.append(settings.OPENCLAW_SERVICE_SECRET_PREVIOUS)
    return secrets


def _extract_user_context(request: Request) -> None:
    """Lift trusted identity headers into request.state for handlers."""
    request.state.user_id = request.headers.get("x-user-id")
    request.state.org_id = request.headers.get("x-org-id")
    request.state.user_role = request.headers.get("x-user-role")


async def service_auth_middleware(request: Request, call_next):
    path = request.url.path

    # CORS preflight — never carries auth; let it through.
    if request.method == "OPTIONS":
        return await call_next(request)

    if _is_public_path(path):
        return await call_next(request)

    valid = _valid_secrets()
    if not valid:
        # Enforcement disabled: still surface any forwarded identity so
        # downstream handlers see the same request.state shape they will
        # see once enforcement is on.
        _extract_user_context(request)
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        logger.warning("service auth: missing bearer on %s %s", request.method, path)
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing service credentials"},
        )

    token = auth[7:].strip()
    if not any(hmac.compare_digest(token, s) for s in valid):
        logger.warning("service auth: invalid token on %s %s", request.method, path)
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid service credentials"},
        )

    _extract_user_context(request)
    return await call_next(request)
