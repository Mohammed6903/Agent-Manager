"""WebSocket JSON-RPC client for the OpenClaw Gateway.

Maintains a single persistent WebSocket connection to the gateway and
multiplexes RPC calls by request id. Device identity (Ed25519 keypair +
gateway-issued deviceToken) is persisted to disk so the server doesn't
need re-approval on every restart.

Auth quirks for openclaw 2026.4.5+ (validated against the working
SimplifiedApi reference client):

  1. ``device.publicKey`` MUST be base64url-encoded *raw 32-byte* Ed25519
     public key — NOT SPKI/DER + standard base64. The gateway derives the
     device id by base64url-decoding this field and taking sha256, then
     comparing to the ``device.id`` we sent. Wrong encoding → device id
     mismatch → auth fails silently with a confusing error.
     See dist/device-identity-*.js → deriveDeviceIdFromPublicKey.

  2. ``client.id`` and ``client.mode`` are enforced against a fixed
     allowlist (GATEWAY_CLIENT_IDS / GATEWAY_CLIENT_MODES in
     dist/message-channel-*.js). For an external backend service the
     correct combination is ``id="gateway-client"`` and ``mode="backend"``.
     Custom values are rejected.

  3. Cron management RPCs (``cron.add`` etc.) require the
     ``operator.admin`` scope, which must be requested at connect time.

  4. Fresh devices are NOT_PAIRED on first connect; the gateway's
     pair-watcher script auto-approves pending requests every few
     seconds, so we retry the handshake a handful of times.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional

import websockets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from fastapi import HTTPException

from ..config import settings
from .gateway_client import GatewayClient

logger = logging.getLogger("agent_manager.clients.ws_gateway")

# ── Allowlisted wire identity ────────────────────────────────────────────
# These two values are NOT free-form. The gateway compares incoming
# client.id / client.mode against a fixed allowlist (see file docstring).
CLIENT_ID = "gateway-client"
CLIENT_MODE = "backend"
CLIENT_VERSION = "1.0.0"

# Scopes requested at connect time. ``operator.admin`` is required for the
# cron management RPCs (cron.add / update / remove etc.); the others cover
# read and write paths used elsewhere.
OPERATOR_SCOPES = ["operator.read", "operator.write", "operator.admin"]

# How long to wait for the gateway pair-watcher to auto-approve a fresh
# device on first connect.
PAIR_RETRY_ATTEMPTS = 6
PAIR_RETRY_DELAY_S = 4.0

# Cold-boot retry budget. Agent lifecycle ops (create/update/restore)
# now use ``agents.create`` / ``agents.update`` which hot-apply without
# a Node restart, so the common case is steady. Retries here remain as
# defense-in-depth for genuine cold-boot windows: installer updates,
# manual restarts, and host reboots. Symptoms when those fire:
#   - fresh connects get ``OSError: Connection refused``
#   - the existing WS we cached is now dead → ``ConnectionClosed`` on
#     the next send.
# Both are safe to retry because (a) ``_connect`` fails before any RPC
# is sent, and (b) ``ConnectionClosed mid-send`` means the request
# bytes never reached the gateway, so there's no side-effect risk of
# retrying. Timeouts (``asyncio.TimeoutError``) are NOT retried because
# the request may have been processed server-side.
# COLD_BOOT_RETRY_DELAYS_S = (0.5, 1.0, 2.0, 4.0)
COLD_BOOT_RETRY_DELAYS_S = (0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _next_id() -> str:
    return uuid.uuid4().hex[:12]


def _looks_like_pairing_error(detail: str) -> bool:
    needles = ("NOT_PAIRED", "PAIRING_REQUIRED", "not-paired", "not_paired", "pairing_required")
    return any(n in detail for n in needles)


class WSGatewayClient(GatewayClient):
    """Persistent multiplexed WebSocket client for the OpenClaw gateway."""

    # Per-server identity filename. Decoupled from the (allowlisted) wire
    # CLIENT_ID so each backend persists its own keypair on disk.
    IDENTITY_NAME = "garage-server"

    REQUEST_TIMEOUT = 30.0
    CONNECT_TIMEOUT = 10.0

    def __init__(self) -> None:
        self._url = self._ws_url()
        self._token = settings.OPENCLAW_GATEWAY_TOKEN or ""
        self._identity_path = (
            Path(settings.OPENCLAW_STATE_DIR) / f"{self.IDENTITY_NAME}-device.json"
        )
        self._identity = self._load_or_create_identity()

        self._ws: Optional[Any] = None  # WebSocketClientProtocol
        self._connect_lock = asyncio.Lock()
        self._reader_task: Optional[asyncio.Task] = None
        self._pending: dict[str, asyncio.Future] = {}
        self._features_methods: set[str] = set()
        self._closed = False

    # ── URL ─────────────────────────────────────────────────────────────

    def _ws_url(self) -> str:
        url = settings.OPENCLAW_GATEWAY_URL
        return url.replace("https://", "wss://").replace("http://", "ws://")

    # ── Device identity (persistent on disk) ────────────────────────────

    def _load_or_create_identity(self) -> dict:
        try:
            data = json.loads(self._identity_path.read_text())
            # Required fields for the new (raw-key, base64url) format.
            if "public_key_b64url" not in data or "private_key_pem" not in data:
                raise KeyError("identity file in legacy format; regenerating")
            priv = serialization.load_pem_private_key(
                data["private_key_pem"].encode(), password=None
            )
            if not isinstance(priv, Ed25519PrivateKey):
                raise ValueError("Stored key is not Ed25519")
            data["_private_key"] = priv
            logger.info(
                "Loaded device identity %s for %s from %s",
                data["device_id"][:12],
                self.IDENTITY_NAME,
                self._identity_path,
            )
            return data
        except FileNotFoundError:
            return self._create_new_identity()
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "Identity file %s missing/incompatible (%s); regenerating",
                self._identity_path,
                exc,
            )
            return self._create_new_identity()

    def _create_new_identity(self) -> dict:
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        # Raw 32-byte public key — used both for the device id and for the
        # publicKey wire field. Encoding here MUST match what the gateway
        # decodes (base64url, no padding).
        raw_pub = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
        device_id = hashlib.sha256(raw_pub).hexdigest()
        priv_pem = priv.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode()

        identity = {
            "identity_name": self.IDENTITY_NAME,
            "device_id": device_id,
            "public_key_b64url": _b64url(raw_pub),
            "private_key_pem": priv_pem,
            "device_token": None,
            "created_at": int(time.time()),
            "_private_key": priv,
        }
        self._save_identity(identity)
        logger.info(
            "Generated new device identity %s for %s at %s "
            "(may require gateway approval on first connect)",
            device_id[:12],
            self.IDENTITY_NAME,
            self._identity_path,
        )
        return identity

    def _save_identity(self, identity: dict) -> None:
        self._identity_path.parent.mkdir(parents=True, exist_ok=True)
        # Strip runtime-only keys before serializing
        to_write = {k: v for k, v in identity.items() if not k.startswith("_")}
        tmp = self._identity_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(to_write, indent=2))
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(self._identity_path)

    # ── Connection management ───────────────────────────────────────────

    async def _ensure_connected(self) -> None:
        if self._ws is not None:
            return
        async with self._connect_lock:
            if self._ws is not None:
                return
            await self._connect_with_pair_retry()

    async def _connect_with_pair_retry(self) -> None:
        """Open the WS and complete the handshake, retrying on NOT_PAIRED.

        A fresh device id will be in PENDING state on the gateway until the
        pair-watcher auto-approves it; we retry the full handshake a few
        times to wait that out.
        """
        last_exc: Optional[HTTPException] = None
        for attempt in range(PAIR_RETRY_ATTEMPTS):
            try:
                await self._connect()
                return
            except HTTPException as exc:
                detail = str(exc.detail)
                if _looks_like_pairing_error(detail):
                    last_exc = exc
                    logger.info(
                        "Gateway pairing not yet approved (attempt %d/%d); "
                        "sleeping %.0fs",
                        attempt + 1,
                        PAIR_RETRY_ATTEMPTS,
                        PAIR_RETRY_DELAY_S,
                    )
                    await asyncio.sleep(PAIR_RETRY_DELAY_S)
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    async def _connect(self) -> None:
        logger.info("Connecting to OpenClaw gateway at %s", self._url)
        try:
            ws = await asyncio.wait_for(
                websockets.connect(self._url, max_size=2**24),
                timeout=self.CONNECT_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Cannot connect to gateway at {self._url}: {exc}",
            )

        try:
            # Step 1: receive challenge
            challenge_raw = await asyncio.wait_for(
                ws.recv(), timeout=self.CONNECT_TIMEOUT
            )
            challenge = json.loads(challenge_raw)
            if challenge.get("event") != "connect.challenge":
                raise HTTPException(
                    status_code=502,
                    detail=f"Expected connect.challenge, got: {str(challenge_raw)[:200]}",
                )
            nonce = challenge["payload"]["nonce"]

            # Step 2: send signed connect request
            await self._send_connect(ws, nonce)

            # Step 3: read until we get the connect response (skip events)
            while True:
                resp_raw = await asyncio.wait_for(
                    ws.recv(), timeout=self.CONNECT_TIMEOUT
                )
                resp = json.loads(resp_raw)
                if resp.get("type") != "res":
                    continue
                if not resp.get("ok"):
                    err = resp.get("payload") or resp.get("error") or {}
                    err_str = json.dumps(err)
                    # If we had a deviceToken and auth failed for a NON-pairing
                    # reason, the token is probably stale. Wipe it so the next
                    # reconnect uses only the keypair + gateway token.
                    if (
                        self._identity.get("device_token")
                        and not _looks_like_pairing_error(err_str)
                    ):
                        logger.warning(
                            "Auth failed with stored deviceToken; clearing it"
                        )
                        self._identity["device_token"] = None
                        self._save_identity(self._identity)
                    raise HTTPException(
                        status_code=502,
                        detail=f"Gateway auth failed: {err_str[:500]}",
                    )

                payload = resp.get("payload", {}) or {}

                # Persist deviceToken from hello-ok for stable reconnects
                auth = payload.get("auth") or {}
                new_token = auth.get("deviceToken")
                if new_token and new_token != self._identity.get("device_token"):
                    self._identity["device_token"] = new_token
                    self._save_identity(self._identity)
                    logger.info("Persisted gateway deviceToken")

                # Cache the advertised method list
                methods = (payload.get("features") or {}).get("methods") or []
                self._features_methods = set(methods)
                if methods:
                    logger.info("Gateway advertises %d RPC methods", len(methods))

                break
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            raise

        self._ws = ws
        self._reader_task = asyncio.create_task(self._reader_loop())
        logger.info(
            "Gateway WS connected (device=%s, identity=%s)",
            self._identity["device_id"][:12],
            self.IDENTITY_NAME,
        )

    async def _send_connect(self, ws: Any, nonce: str) -> None:
        signed_at = int(time.time() * 1000)
        scopes_str = ",".join(OPERATOR_SCOPES)
        payload_str = "|".join(
            [
                "v3",
                self._identity["device_id"],
                CLIENT_ID,
                CLIENT_MODE,
                "operator",      # role
                scopes_str,
                str(signed_at),
                self._token,
                nonce,
                "linux",
                "server",
            ]
        )
        signature = self._identity["_private_key"].sign(payload_str.encode("utf-8"))

        auth_obj: dict = {}
        if self._token:
            auth_obj["token"] = self._token
        if self._identity.get("device_token"):
            auth_obj["deviceToken"] = self._identity["device_token"]

        msg = {
            "type": "req",
            "id": _next_id(),
            "method": "connect",
            "params": {
                "minProtocol": 3,
                "maxProtocol": 3,
                "client": {
                    "id": CLIENT_ID,
                    "version": CLIENT_VERSION,
                    "platform": "linux",
                    "deviceFamily": "server",
                    "mode": CLIENT_MODE,
                },
                "role": "operator",
                "scopes": OPERATOR_SCOPES,
                "caps": [],
                "commands": [],
                "permissions": {},
                "auth": auth_obj,
                "locale": "en-US",
                "userAgent": f"{CLIENT_ID}/{CLIENT_VERSION}",
                "device": {
                    "id": self._identity["device_id"],
                    "publicKey": self._identity["public_key_b64url"],
                    "signature": _b64url(signature),
                    "signedAt": signed_at,
                    "nonce": nonce,
                },
            },
        }
        await ws.send(json.dumps(msg))

    async def _reader_loop(self) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if msg.get("type") != "res":
                    continue  # ignore events / ticks
                fut = self._pending.pop(msg.get("id", ""), None)
                if fut is None or fut.done():
                    continue
                if msg.get("ok"):
                    fut.set_result(msg.get("payload", {}))
                else:
                    err = msg.get("payload") or msg.get("error") or {}
                    fut.set_exception(
                        HTTPException(
                            status_code=500,
                            detail=f"Gateway RPC error: {json.dumps(err)[:500]}",
                        )
                    )
        except websockets.exceptions.ConnectionClosed as exc:
            logger.warning("Gateway WS closed: %s", exc)
        except Exception as exc:
            logger.exception("Gateway WS reader crashed: %s", exc)
        finally:
            self._ws = None
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(
                        HTTPException(
                            status_code=502,
                            detail="Gateway connection closed",
                        )
                    )
            self._pending.clear()

    # Detail strings raised from _call_once that indicate the connection
    # failed before the request reached the gateway. Safe to retry.
    _COLD_BOOT_DETAIL_PREFIXES = (
        "Cannot connect to gateway",
        "Gateway connection closed mid-send",
        "Gateway connection unavailable",
    )

    async def _call(self, method: str, params: dict) -> Any:
        """Invoke an RPC, retrying on gateway cold-boot failures.

        Steady-state agent ops (create/update/restore) now use
        ``agents.create``/``agents.update``, which hot-apply without a
        Node restart. Retries here cover genuine cold boots: installer
        ``update.run`` respawns, manual restarts, host reboots — which
        either (a) kill our cached WS or (b) refuse new connects while
        booting. Both are retried per ``COLD_BOOT_RETRY_DELAYS_S``.
        Other failures (timeout, 4xx-style RPC errors, auth) are not.
        """
        last_exc: HTTPException | None = None
        for attempt, delay in enumerate((0.0, *COLD_BOOT_RETRY_DELAYS_S)):
            if delay:
                await asyncio.sleep(delay)
            try:
                return await self._call_once(method, params)
            except HTTPException as exc:
                detail_str = str(exc.detail)
                is_cold_boot = exc.status_code == 502 and any(
                    detail_str.startswith(p) for p in self._COLD_BOOT_DETAIL_PREFIXES
                )
                if not is_cold_boot:
                    raise
                # Wipe the cached WS so the next attempt reconnects fresh.
                # _reader_loop should clear it too, but racing its
                # cleanup in every caller is fragile — do it here.
                if self._ws is not None:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                last_exc = exc
                logger.warning(
                    "Gateway RPC %s failed on attempt %d (%s); retrying",
                    method, attempt + 1, detail_str,
                )
        assert last_exc is not None
        raise last_exc

    async def _call_once(self, method: str, params: dict) -> Any:
        await self._ensure_connected()
        ws = self._ws
        if ws is None:
            raise HTTPException(
                status_code=502, detail="Gateway connection unavailable"
            )

        if self._features_methods and method not in self._features_methods:
            logger.warning(
                "Calling method %r which gateway did not advertise in features.methods",
                method,
            )

        req_id = _next_id()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut

        try:
            await ws.send(
                json.dumps(
                    {"type": "req", "id": req_id, "method": method, "params": params}
                )
            )
        except websockets.exceptions.ConnectionClosed:
            self._pending.pop(req_id, None)
            raise HTTPException(
                status_code=502, detail="Gateway connection closed mid-send"
            )

        try:
            return await asyncio.wait_for(fut, timeout=self.REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise HTTPException(
                status_code=504, detail=f"Gateway RPC timeout for {method}"
            )

    async def aclose(self) -> None:
        self._closed = True
        if self._reader_task:
            self._reader_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ── GatewayClient interface ─────────────────────────────────────────

    async def list_agents(self) -> List[dict]:
        data = await self._call("agents.list", {})
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("agents", "list", "items", "payload", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            if "id" in data:
                return [data]
        return []

    async def get_config(self) -> dict:
        return await self._call("config.get", {})

    async def create_agent_record(
        self, agent_id: str, name: str, workspace: str
    ) -> dict:
        # The gateway derives ``agentId = normalizeAgentId(name)``. Our
        # ``agent_id`` is already validated to ``^[a-z0-9]+$`` and passes
        # through normalization unchanged, so we send ``name=agent_id`` to
        # pin the gateway-side id, then ``agents.update`` to set the
        # human-readable display name. Two RPCs, no SIGUSR1 — unlike the
        # legacy ``config.patch`` path this replaces.
        await self._call(
            "agents.create", {"name": agent_id, "workspace": workspace}
        )
        if name and name != agent_id:
            return await self._call(
                "agents.update", {"agentId": agent_id, "name": name}
            )
        return {"ok": True, "agentId": agent_id}

    async def update_agent_record(
        self,
        agent_id: str,
        name: Optional[str] = None,
        workspace: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {"agentId": agent_id}
        if name is not None:
            params["name"] = name
        if workspace is not None:
            params["workspace"] = workspace
        if model is not None:
            params["model"] = model
        return await self._call("agents.update", params)

    async def delete_agent(self, agent_id: str) -> dict:
        return await self._call(
            "agents.delete", {"agentId": agent_id, "force": True}
        )

    async def get_status(self) -> dict:
        return await self._call("status", {})

    # ── Cron ────────────────────────────────────────────────────────────

    async def cron_list(self) -> List[dict]:
        data = await self._call("cron.list", {"includeDisabled": True})
        if isinstance(data, dict):
            return data.get("jobs", [])
        if isinstance(data, list):
            return data
        return []

    async def cron_add(self, job: dict) -> dict:
        params: dict[str, Any] = {
            "name": job.get("name", ""),
            "sessionTarget": job.get("sessionTarget", "isolated"),
            "enabled": job.get("enabled", True),
            "deleteAfterRun": bool(job.get("deleteAfterRun", False)),
        }
        if job.get("agentId"):
            params["agentId"] = job["agentId"]
        if job.get("description"):
            params["description"] = job["description"]

        # Schedule
        schedule = job.get("schedule") or {}
        kind = schedule.get("kind")
        if kind == "cron":
            params["schedule"] = {
                "kind": "cron",
                "expr": schedule.get("expr", ""),
                "tz": schedule.get("tz", "UTC"),
            }
        elif kind == "every":
            every = schedule.get("everyMs") or schedule.get("every") or 0
            params["schedule"] = {"kind": "every", "everyMs": int(every)}
        elif kind == "at":
            at = schedule.get("atMs") or schedule.get("at") or 0
            params["schedule"] = {"kind": "at", "atMs": int(at)}
        else:
            params["schedule"] = schedule

        # Payload — callers store text in `message` for both kinds, but the
        # spec uses `text` for systemEvent.
        payload = dict(job.get("payload") or {})
        if (
            payload.get("kind") == "systemEvent"
            and "message" in payload
            and "text" not in payload
        ):
            payload["text"] = payload.pop("message")
        params["payload"] = payload

        delivery = job.get("delivery") or {}
        if delivery:
            params["delivery"] = delivery

        result = await self._call("cron.add", params)
        if isinstance(result, dict):
            job_id = result.get("jobId") or result.get("id")
            if job_id:
                result["jobId"] = job_id
                result["id"] = job_id
        return result

    async def cron_update(self, job_id: str, patch: dict) -> dict:
        return await self._call(
            "cron.update", {"jobId": job_id, "patch": patch}
        )

    async def cron_edit(self, job_id: str, updates: dict) -> dict:
        patch: dict[str, Any] = {}
        if "enabled" in updates:
            patch["enabled"] = updates["enabled"]
        if "name" in updates:
            patch["name"] = updates["name"]

        sched = updates.get("schedule")
        if sched:
            kind = sched.get("kind")
            if kind == "cron":
                patch["schedule"] = {
                    "kind": "cron",
                    "expr": sched.get("expr", ""),
                    "tz": sched.get("tz", "UTC"),
                }
            elif kind == "every":
                every = sched.get("everyMs") or sched.get("every") or 0
                patch["schedule"] = {"kind": "every", "everyMs": int(every)}
            elif kind == "at":
                at = sched.get("atMs") or sched.get("at") or 0
                patch["schedule"] = {"kind": "at", "atMs": int(at)}
            else:
                patch["schedule"] = sched

        pl = updates.get("payload")
        if pl:
            pl = dict(pl)
            if (
                pl.get("kind") == "systemEvent"
                and "message" in pl
                and "text" not in pl
            ):
                pl["text"] = pl.pop("message")
            patch["payload"] = pl

        return await self._call(
            "cron.update", {"jobId": job_id, "patch": patch}
        )

    async def cron_remove(self, job_id: str) -> dict:
        return await self._call("cron.remove", {"jobId": job_id})

    async def cron_run(self, job_id: str) -> dict:
        return await self._call("cron.run", {"jobId": job_id, "mode": "force"})

    async def cron_runs(self, job_id: str, limit: int = 20) -> List[dict]:
        data = await self._call(
            "cron.runs", {"jobId": job_id, "limit": limit}
        )
        if isinstance(data, dict):
            return data.get("entries", data.get("runs", []))
        if isinstance(data, list):
            return data
        return []
