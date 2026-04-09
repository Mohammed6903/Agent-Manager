"""Thin async wrapper over Telnyx Call Control v2 REST API.

Only the methods we use for outbound voice calls are implemented:

- initiate_call       POST /v2/calls
- streaming_start     POST /v2/calls/{cci}/actions/streaming_start
- hangup              POST /v2/calls/{cci}/actions/hangup
- get_call            GET  /v2/calls/{cci}

Inbound handling, DTMF, recording, and other actions are deliberately out of
scope for Phase 1.

Docs: https://developers.telnyx.com/api/call-control/v2
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telnyx.com/v2"
# Generous connect timeout because OpenClawApi runs in India and Telnyx is in
# the US — international TCP+TLS handshakes need multiple round trips, and a
# packet-loss spike easily blows past 5 s. Read timeout stays modest because
# Telnyx API responses are fast once connected.
DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=15.0)
# Retry budget for transient connect-stage failures (DNS / TCP / TLS).
# Only applies to requests that go through ``_post_with_retry``.
_CONNECT_RETRIES = 2  # initial attempt + 2 retries = 3 total
_CONNECT_RETRY_BACKOFF_S = 1.0


class TelnyxError(Exception):
    """Raised when the Telnyx API returns an error response."""

    def __init__(self, status: int, detail: str, code: Optional[str] = None):
        super().__init__(f"Telnyx API error {status}: {detail}")
        self.status = status
        self.detail = detail
        self.code = code


class TelnyxClient:
    """Async Telnyx Call Control client. Short-lived httpx clients per call."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        connection_id: Optional[str] = None,
        from_number: Optional[str] = None,
    ):
        self.api_key = api_key or settings.TELNYX_API_KEY
        self.connection_id = connection_id or settings.TELNYX_CONNECTION_ID
        self.from_number = from_number or settings.TELNYX_FROM_NUMBER

        if not self.api_key:
            raise RuntimeError("TELNYX_API_KEY not configured")
        if not self.connection_id:
            raise RuntimeError("TELNYX_CONNECTION_ID not configured")
        if not self.from_number:
            raise RuntimeError("TELNYX_FROM_NUMBER not configured")

    # ── Internal request helpers ────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _post(
        self, path: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Single-attempt POST. Use ``_post_with_retry`` for critical actions."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{BASE_URL}{path}",
                json=body,
                headers=self._headers(),
            )
        return self._parse(resp)

    async def _post_with_retry(
        self, path: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """POST with retries on connect-stage failures.

        Retries are safe for connect-stage failures (DNS / TCP / TLS) because
        the request never reached the server, so there's no risk of duplicate
        side effects. Once we get a real HTTP response (even a 5xx), we
        return / raise immediately — never retry past the connect stage.
        """
        last_exc: Exception | None = None
        for attempt in range(_CONNECT_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    resp = await client.post(
                        f"{BASE_URL}{path}",
                        json=body,
                        headers=self._headers(),
                    )
                return self._parse(resp)
            except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt >= _CONNECT_RETRIES:
                    break
                wait = _CONNECT_RETRY_BACKOFF_S * (2 ** attempt)
                logger.warning(
                    "Telnyx %s connect failed (attempt %d/%d): %s — retrying in %.1fs",
                    path,
                    attempt + 1,
                    _CONNECT_RETRIES + 1,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
        # All retries exhausted
        logger.error(
            "Telnyx %s connect failed after %d attempts: %s",
            path,
            _CONNECT_RETRIES + 1,
            last_exc,
        )
        raise last_exc  # type: ignore[misc]

    async def _get(self, path: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_URL}{path}",
                headers=self._headers(),
            )
        return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> Dict[str, Any]:
        try:
            payload = resp.json()
        except Exception:
            payload = {}

        if resp.status_code >= 400:
            errors = payload.get("errors") or []
            detail = (
                errors[0].get("detail")
                if errors
                else resp.text or f"HTTP {resp.status_code}"
            )
            code = errors[0].get("code") if errors else None
            logger.warning(
                "Telnyx API %s → HTTP %s: %s (code=%s)",
                resp.request.url.path,
                resp.status_code,
                detail,
                code,
            )
            raise TelnyxError(resp.status_code, str(detail), code=str(code) if code else None)

        # Telnyx sometimes returns `errors` alongside a 2xx response (D38 did this).
        if payload.get("errors"):
            first = payload["errors"][0]
            detail = first.get("detail", "unknown")
            code = first.get("code")
            logger.warning(
                "Telnyx API %s succeeded with error payload: %s (code=%s)",
                resp.request.url.path,
                detail,
                code,
            )
            raise TelnyxError(resp.status_code, str(detail), code=str(code) if code else None)

        return payload.get("data", {}) if isinstance(payload, dict) else {}

    # ── Public methods ──────────────────────────────────────────────────────

    async def initiate_call(
        self,
        *,
        to: str,
        webhook_url: str,
        client_state: Optional[str] = None,
        timeout_secs: int = 30,
    ) -> Dict[str, Any]:
        """POST /v2/calls — place an outbound call.

        Returns the `data` block: {call_control_id, call_leg_id, call_session_id, ...}.
        """
        body: Dict[str, Any] = {
            "connection_id": self.connection_id,
            "to": to,
            "from": self.from_number,
            "webhook_url": webhook_url,
            "webhook_url_method": "POST",
            "timeout_secs": timeout_secs,
        }
        if client_state:
            # Telnyx wants base64-encoded arbitrary state that it echoes on every event.
            import base64

            body["client_state"] = base64.b64encode(client_state.encode()).decode()

        return await self._post_with_retry("/calls", body)

    async def streaming_start(
        self,
        *,
        call_control_id: str,
        stream_url: str,
        stream_track: str = "inbound_track",
    ) -> Dict[str, Any]:
        """POST /v2/calls/{cci}/actions/streaming_start — open media stream.

        Uses Telnyx defaults: **PCMU (μ-law) @ 8 kHz** in both directions.
        This is the universal telephony codec and the configuration used
        by Telnyx's own official voice-AI demo (``demo-python-telnyx/
        fastapi-v2v-over-media-streaming``) and by pipecat's production
        Telnyx serializer.

        We do NOT specify ``stream_bidirectional_codec`` — letting Telnyx
        default avoids the L16/HD codec rabbit hole that we tried earlier
        and abandoned (no working public reference exists, even pipecat's
        L16 PR is unmerged). PCMU 8 kHz is the validated path.

        Bidirectional streaming is enabled via ``stream_bidirectional_mode``,
        which lets us push outbound TTS audio frames back over the same
        WebSocket — Telnyx mixes them into the call's outbound path.

        Track selection notes:
        - ``inbound_track``  → only the caller's audio (we get user speech only)
        - ``outbound_track`` → only our own audio (useless for STT)
        - ``both_tracks``    → both sides interleaved
        """
        body = {
            "stream_url": stream_url,
            "stream_track": stream_track,
            "stream_bidirectional_mode": "rtp",
        }
        return await self._post_with_retry(
            f"/calls/{call_control_id}/actions/streaming_start", body
        )

    async def streaming_stop(self, *, call_control_id: str) -> Dict[str, Any]:
        return await self._post(
            f"/calls/{call_control_id}/actions/streaming_stop",
            {},
        )

    async def speak(
        self,
        *,
        call_control_id: str,
        text: str,
        voice: str = "Polly.Joanna",
        language: str = "en-US",
    ) -> Dict[str, Any]:
        """POST /v2/calls/{cci}/actions/speak — server-side TTS via Polly.

        Telnyx queues the speech and fires `call.speak.started` then
        `call.speak.ended` webhook events. Returns immediately; does not
        block until speech completes.
        """
        return await self._post_with_retry(
            f"/calls/{call_control_id}/actions/speak",
            {
                "command_id": str(uuid.uuid4()),
                "payload": text,
                "voice": voice,
                "language": language,
            },
        )

    async def transcription_start(
        self,
        *,
        call_control_id: str,
        language: str = "en",
        interim_results: bool = False,
        transcription_engine: str = "B",
    ) -> Dict[str, Any]:
        """POST /v2/calls/{cci}/actions/transcription_start — server-side STT.

        Telnyx fires `call.transcription` webhook events with the user's
        utterances. With ``interim_results=False``, only final transcripts
        are delivered.

        ``transcription_engine``:
            - ``"A"`` = Google Speech-to-Text
            - ``"B"`` = Telnyx's own ASR (default — typically tuned better
                       for Telnyx's audio path)
        """
        return await self._post(
            f"/calls/{call_control_id}/actions/transcription_start",
            {
                "command_id": str(uuid.uuid4()),
                "language": language,
                "interim_results": interim_results,
                "transcription_engine": transcription_engine,
            },
        )

    async def transcription_stop(
        self, *, call_control_id: str
    ) -> Dict[str, Any]:
        """POST /v2/calls/{cci}/actions/transcription_stop — halt server-side STT."""
        try:
            return await self._post(
                f"/calls/{call_control_id}/actions/transcription_stop",
                {"command_id": str(uuid.uuid4())},
            )
        except TelnyxError as e:
            if e.status == 404:
                return {}
            raise

    async def hangup(self, *, call_control_id: str) -> Dict[str, Any]:
        try:
            return await self._post(
                f"/calls/{call_control_id}/actions/hangup", {}
            )
        except TelnyxError as e:
            # 404 on hangup means the call is already gone; not an error from our perspective.
            if e.status == 404:
                return {}
            raise

    async def get_call(self, *, call_control_id: str) -> Dict[str, Any]:
        return await self._get(f"/calls/{call_control_id}")
