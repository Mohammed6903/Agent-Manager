"""Telnyx webhook signature verification (Ed25519).

Telnyx signs `timestamp|payload` with its per-application private key and
sends two headers:

    telnyx-signature-ed25519   — base64 signature
    telnyx-timestamp            — unix seconds

We verify using the public key configured as TELNYX_PUBLIC_KEY. The key is
delivered by Telnyx as a raw base64 Ed25519 public key (32 bytes), not a PEM.

Also enforces a freshness window (default 5 min) to reduce replay risk.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Mapping, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..config import settings

logger = logging.getLogger(__name__)

DEFAULT_MAX_SKEW_SEC = 300


@dataclass
class VerificationResult:
    ok: bool
    reason: Optional[str] = None
    timestamp: Optional[int] = None


def verify_telnyx_webhook(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    public_key_b64: Optional[str] = None,
    max_skew_sec: int = DEFAULT_MAX_SKEW_SEC,
) -> VerificationResult:
    """Verify a Telnyx webhook request.

    Args:
        raw_body: The request body bytes as delivered (signature is over bytes,
                  not the parsed JSON). Must NOT be re-serialized.
        headers: Request headers (FastAPI's request.headers works directly).
        public_key_b64: The base64-encoded Ed25519 public key Telnyx provides.
                        Defaults to settings.TELNYX_PUBLIC_KEY.
        max_skew_sec: Max acceptable clock skew between Telnyx and us.

    Returns:
        VerificationResult.ok=True only if the signature is valid AND the
        timestamp is within the skew window.
    """
    public_key_b64 = public_key_b64 or settings.TELNYX_PUBLIC_KEY
    if not public_key_b64:
        return VerificationResult(
            ok=False,
            reason="TELNYX_PUBLIC_KEY not configured — cannot verify webhook",
        )

    # FastAPI / Starlette headers are case-insensitive but normalize to lower.
    signature_b64 = headers.get("telnyx-signature-ed25519")
    timestamp_str = headers.get("telnyx-timestamp")
    if not signature_b64 or not timestamp_str:
        return VerificationResult(
            ok=False,
            reason="Missing telnyx-signature-ed25519 or telnyx-timestamp header",
        )

    try:
        event_time_sec = int(timestamp_str)
    except ValueError:
        return VerificationResult(ok=False, reason="Invalid timestamp header")

    try:
        public_key_bytes = base64.b64decode(public_key_b64)
        key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    except Exception as exc:
        return VerificationResult(
            ok=False, reason=f"Invalid public key: {exc}"
        )

    try:
        signature = base64.b64decode(signature_b64)
    except Exception as exc:
        return VerificationResult(ok=False, reason=f"Invalid signature encoding: {exc}")

    # Telnyx signs: "{timestamp}|{raw_body}"
    # Important: raw_body is bytes, but we concat with a text prefix.
    signed_payload = timestamp_str.encode("ascii") + b"|" + raw_body

    try:
        key.verify(signature, signed_payload)
    except InvalidSignature:
        return VerificationResult(ok=False, reason="Invalid signature")
    except Exception as exc:
        return VerificationResult(ok=False, reason=f"Verification error: {exc}")

    now_sec = int(time.time())
    if abs(now_sec - event_time_sec) > max_skew_sec:
        return VerificationResult(
            ok=False,
            reason=f"Timestamp too old (skew {now_sec - event_time_sec}s > max {max_skew_sec}s)",
            timestamp=event_time_sec,
        )

    return VerificationResult(ok=True, timestamp=event_time_sec)
