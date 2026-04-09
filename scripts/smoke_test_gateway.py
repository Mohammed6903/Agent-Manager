"""Smoke test for the WSGatewayClient against a live OpenClaw gateway.

Run from the OpenClawApi directory:
    python -m scripts.smoke_test_gateway

Verifies the connect handshake, persistent device identity, and a few
read-only RPC round-trips. Does NOT mutate any state on the gateway.

To verify the per-agent tool filtering pilot (Layer 1), pass two agent
ids and the integration name to check via env vars:
    SMOKE_AGENT_WITH=<agent_id_with_integration> \
    SMOKE_AGENT_WITHOUT=<agent_id_without_integration> \
    SMOKE_INTEGRATION=gmail \
    python -m scripts.smoke_test_gateway

Exit code 0 = all checks passed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from agent_manager.clients.ws_gateway_client import WSGatewayClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("smoke_test")


async def main() -> int:
    gw = WSGatewayClient()
    failures: list[str] = []

    async def check(name: str, coro):
        try:
            result = await coro
            preview = json.dumps(result, default=str)[:200]
            print(f"  ✓ {name}: {preview}")
            return result
        except Exception as exc:
            print(f"  ✗ {name}: {type(exc).__name__}: {exc}")
            failures.append(name)
            return None

    print(f"Gateway URL: {gw._url}")
    print(f"Identity:    {gw._identity_path}")
    print(f"Device ID:   {gw._identity['device_id'][:16]}...")
    print(f"Has token:   {bool(gw._identity.get('device_token'))}")
    print()
    print("Round 1 — first connect (may trigger device approval if new):")
    await check("get_status", gw.get_status())
    await check("list_agents", gw.list_agents())
    await check("get_config", gw.get_config())
    await check("cron_list", gw.cron_list())

    print()
    print("Round 2 — same connection (multiplex check):")
    # Fire 5 calls concurrently to verify the reader-loop multiplexes correctly
    results = await asyncio.gather(
        gw.get_status(),
        gw.cron_list(),
        gw.get_status(),
        gw.cron_list(),
        gw.get_status(),
        return_exceptions=True,
    )
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"  ✗ concurrent[{i}]: {type(r).__name__}: {r}")
            failures.append(f"concurrent[{i}]")
        else:
            print(f"  ✓ concurrent[{i}] ok")

    print()
    print(f"Advertised methods: {len(gw._features_methods)}")
    interesting = [
        m for m in sorted(gw._features_methods)
        if m.startswith(("agents.", "config.", "cron.", "status"))
    ]
    print(f"Relevant: {interesting}")

    # ── Layer 1 per-agent tool filter check ────────────────────────────
    # Verifies the agent-manager-extension factory pilot: an agent without
    # the configured integration should not see its tools after the plugin's
    # cache has warmed; an agent with it should see them.
    agent_with = os.environ.get("SMOKE_AGENT_WITH")
    agent_without = os.environ.get("SMOKE_AGENT_WITHOUT")
    integration = os.environ.get("SMOKE_INTEGRATION", "gmail")
    if agent_with or agent_without:
        prefix = f"{integration}_"
        print()
        print(f"Round 3 — per-agent tool filtering (integration={integration}):")

        # tools.effective requires agentId and sessionKey to MATCH a real
        # active session (the gateway resolves the session and rejects
        # mismatched/synthesized keys). Look up real sessions via
        # sessions.list and parse the agent id out of the key —
        # openclaw key format is "agent:<agentId>:<scope>:<channel>:<uuid>".
        sessions_resp = await gw._call("sessions.list", {})

        sessions_by_agent: dict[str, str] = {}
        candidates: list = []
        if isinstance(sessions_resp, list):
            candidates = sessions_resp
        elif isinstance(sessions_resp, dict):
            for key in ("sessions", "items", "entries", "list", "data"):
                v = sessions_resp.get(key)
                if isinstance(v, list):
                    candidates = v
                    break

        for s in candidates:
            if not isinstance(s, dict):
                continue
            skey = (
                s.get("sessionKey")
                or s.get("session_key")
                or s.get("key")
                or s.get("id")
                or s.get("sessionId")
            )
            # Try explicit agentId first, then parse from "agent:<agentId>:..." key
            aid = s.get("agentId") or s.get("agent_id") or s.get("agent")
            if not aid and isinstance(skey, str) and skey.startswith("agent:"):
                parts = skey.split(":", 2)
                if len(parts) >= 2:
                    aid = parts[1]
            if aid and skey and aid not in sessions_by_agent:
                sessions_by_agent[aid] = skey

        print(f"  (resolved {len(sessions_by_agent)} agent→session mappings)")
        for aid, skey in sessions_by_agent.items():
            print(f"    {aid[:32]}… → {skey[:64]}…")

        async def integration_tools_for(agent_id: str) -> tuple[list[str], bool]:
            """Return (tool_list, success). success=False on RPC error or no session."""
            session_key = sessions_by_agent.get(agent_id)
            if not session_key:
                print(f"    no session found for agent={agent_id[:24]}… "
                      f"(start a chat with this agent at least once, then re-run)")
                return ([], False)
            # Three calls with longer waits: first triggers cold-start
            # (factory fails open + async backend fetch), then we wait
            # 1s for the cache to populate, second confirms the warm
            # path, third sanity check.
            tools: list[str] = []
            for attempt in range(3):
                try:
                    resp = await gw._call(
                        "tools.effective",
                        {"agentId": agent_id, "sessionKey": session_key},
                    )
                except Exception as exc:
                    print(f"    attempt {attempt + 1}: tools.effective failed: {exc}")
                    return ([], False)
                tools = []
                for group in resp.get("groups", []) or []:
                    for tool in group.get("tools", []) or []:
                        name = tool.get("id") or tool.get("name") or ""
                        if name.startswith(prefix):
                            tools.append(name)
                print(f"    attempt {attempt + 1} (session={session_key[:32]}…): "
                      f"{len(tools)} {prefix}* tools")
                if attempt < 2:
                    await asyncio.sleep(1.0)
            return (sorted(tools), True)

        if agent_without:
            found, ok = await integration_tools_for(agent_without)
            if not ok:
                print(f"  ✗ agent_without ({agent_without[:16]}…) "
                      f"check could not run (no session or RPC error)")
                failures.append(f"filter_excludes_{integration}_setup")
            elif found:
                print(f"  ✗ agent_without ({agent_without[:16]}…) "
                      f"saw {len(found)} {prefix}* tools, expected 0: {found}")
                failures.append(f"filter_excludes_{integration}")
            else:
                print(f"  ✓ agent_without ({agent_without[:16]}…) "
                      f"saw 0 {prefix}* tools (filter applied)")

        if agent_with:
            found, ok = await integration_tools_for(agent_with)
            if not ok:
                print(f"  ✗ agent_with ({agent_with[:16]}…) "
                      f"check could not run (no session or RPC error)")
                failures.append(f"filter_includes_{integration}_setup")
            elif len(found) >= 1:
                print(f"  ✓ agent_with ({agent_with[:16]}…) "
                      f"saw {len(found)} {prefix}* tools: {found}")
            else:
                print(f"  ✗ agent_with ({agent_with[:16]}…) "
                      f"saw 0 {prefix}* tools, expected ≥1")
                failures.append(f"filter_includes_{integration}")
    else:
        print()
        print("(Skipping per-agent filter check — set SMOKE_AGENT_WITH, "
              "SMOKE_AGENT_WITHOUT, and SMOKE_INTEGRATION to enable)")

    await gw.aclose()

    print()
    if failures:
        print(f"FAIL — {len(failures)} check(s) failed: {failures}")
        return 1
    print("OK — all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
