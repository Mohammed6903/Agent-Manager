"""Voice-call HTTP + WebSocket routes.

Endpoints:

    POST   /api/voice/call                         Initiate outbound call
    GET    /api/voice/call/{id}                    Get call + turns
    GET    /api/voice/calls                        List recent calls
    POST   /api/voice/webhooks/telnyx              Telnyx event webhook (signature verified)
    WS     /api/voice/stream/{call_id}             Telnyx media stream (audio frames)

The HTTP endpoints are unauthenticated to match OpenClawApi's upstream-handled
auth pattern. The webhook endpoint verifies Telnyx's Ed25519 signature on
every request, which is effectively auth of a different flavor — only Telnyx
can produce a valid signature.
"""

from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    Query,
    Request,
    WebSocket,
    status,
)
from sqlalchemy.orm import Session

from ..database import get_db
from .media_stream import handle_media_stream
from .schemas import CallView, InitiateCallRequest, InitiateCallResponse
from .service import VoiceCallService
from .webhook_security import verify_telnyx_webhook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Voice Call"])


def _get_service(db: Session = Depends(get_db)) -> VoiceCallService:
    return VoiceCallService(db)


# ── Outbound initiation ─────────────────────────────────────────────────────


@router.post(
    "/call",
    response_model=InitiateCallResponse,
    status_code=status.HTTP_201_CREATED,
    # TODO: add route auth when OpenClawApi gets proper auth middleware
)
async def initiate_call(
    req: InitiateCallRequest,
    svc: VoiceCallService = Depends(_get_service),
):
    try:
        return await svc.initiate_outbound(req)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to initiate voice call: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Introspection ───────────────────────────────────────────────────────────


@router.get("/call/{call_id}", response_model=CallView)
def get_call(
    call_id: str,
    svc: VoiceCallService = Depends(_get_service),
):
    view = svc.get_call(call_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return view


@router.get("/calls", response_model=list[CallView])
def list_calls(
    limit: int = Query(default=20, ge=1, le=200),
    svc: VoiceCallService = Depends(_get_service),
):
    return svc.list_calls(limit=limit)


# ── Telnyx webhook ──────────────────────────────────────────────────────────


@router.post("/webhooks/telnyx", status_code=200)
async def telnyx_webhook(
    request: Request,
    svc: VoiceCallService = Depends(_get_service),
):
    """Receive call lifecycle events from Telnyx.

    Signature is verified using the Ed25519 public key configured as
    TELNYX_PUBLIC_KEY. Any tampering or replay attempt returns 401.
    """
    raw_body = await request.body()

    result = verify_telnyx_webhook(
        raw_body=raw_body,
        headers={k.lower(): v for k, v in request.headers.items()},
    )
    if not result.ok:
        logger.warning("Rejecting Telnyx webhook: %s", result.reason)
        raise HTTPException(status_code=401, detail=result.reason or "invalid signature")

    try:
        import json

        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as exc:
        logger.warning("Malformed Telnyx webhook JSON: %s", exc)
        raise HTTPException(status_code=400, detail="malformed payload")

    try:
        await svc.handle_webhook_event(payload)
    except Exception:
        logger.exception(
            "Voice call webhook handler crashed for event %s",
            (payload.get("data") or {}).get("event_type"),
        )
        # Return 200 anyway — Telnyx retries on non-2xx, and we don't want
        # replays to flood our DB. We logged the error, which is enough.

    return {"ok": True}


# ── Media stream WebSocket ──────────────────────────────────────────────────


@router.websocket("/stream/{call_id}")
async def media_stream_ws(websocket: WebSocket, call_id: str):
    """Telnyx media stream endpoint.

    Telnyx connects here after we call /actions/streaming_start. The
    connection carries bidirectional PCM audio for the call.
    """
    await handle_media_stream(websocket, call_id=call_id)
