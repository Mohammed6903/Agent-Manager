"""Voice-call ↔ openclaw agent bridge with client-side tool execution.

Each voice call gets its own VoiceAgentSession which holds:

- A stable session key (ties the conversation to openclaw's per-session memory)
- The rolling message history (so multi-turn conversations have context)
- A reference to the agent_id that should handle the call

The agent turn loop:

1. POST the conversation to openclaw's ``/v1/chat/completions`` endpoint
2. Parse the assistant reply for tool-call markup. Two formats seen in the wild:
    a. XML markup:        ``<tool_call>{...}</tool_call>``
    b. Function-call:     ``task_create({...})``
3. If tool calls found:
    - Execute each via openclaw's ``/tools/invoke`` HTTP endpoint
    - Append the (assistant tool-call message, user "tool result" message) pair
      to the session history
    - Loop back to step 1
4. If no tool calls (just natural language) → return the text. The caller
   speaks it via Voxtral TTS.

The reason this is in our code rather than openclaw's: openclaw's Mistral
adapter currently doesn't recognize Mistral large's function-call format
(it gets emitted in the assistant ``content`` field, not the structured
``tool_calls`` field). So tool calls fall through as text, and Voxtral
ends up speaking JSON. We intercept here and execute the tools ourselves.

Loop is capped at ``MAX_TOOL_ITERATIONS`` to prevent infinite agent loops.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# Maximum number of tool execution iterations per user turn. If the agent
# keeps invoking tools after this many rounds, we return whatever's in
# its last reply (probably mid-thought) and let the caller speak it.
MAX_TOOL_ITERATIONS = 5

# Per-iteration timeout for the chat completions HTTP call. The total turn
# can take up to MAX_TOOL_ITERATIONS × this if every iteration is slow.
DEFAULT_AGENT_TIMEOUT_S = 180.0
TOOLS_INVOKE_TIMEOUT_S = 60.0


@dataclass
class VoiceAgentSession:
    """Per-call agent conversation state.

    The ``user_field`` is openclaw's session disambiguator AND its way of
    identifying the human user the agent is acting on behalf of. The chat
    service builds it as ``"{agent_id}:{user_id}"`` (with optional
    ``:{session_id}`` suffix) — openclaw extracts ``user_id`` from the
    second segment to look up wallet, integrations (Gmail, Calendar, etc.)
    and other user-scoped resources. **The voice path MUST follow the
    same shape**, otherwise tools that need user context (send_email,
    schedule_event, anything reading user state) silently get no user
    and either fail or operate without authorization.

    For voice calls we use ``"{agent_id}:{user_id}:voice:{call_id}"`` so
    each call gets its own per-session conversation history while still
    being correctly attributed to the user.
    """

    call_id: str
    agent_id: str
    user_id: Optional[str] = None
    system_prompt: Optional[str] = None
    messages: list[dict] = field(default_factory=list)

    @property
    def user_field(self) -> str:
        # Match agent_manager.services.chat_service._build_user_field shape
        # exactly: {agent_id}:{user_id}[:{session_id}]. We use the call_id
        # as the session_id so each voice call has an isolated conversation.
        # If user_id is missing, fall back to a per-call placeholder so
        # openclaw still gets a parseable string (no crash) but tools that
        # need a real user will report the error rather than silently
        # acting on the wrong user.
        uid = self.user_id or "unknown"
        return f"{self.agent_id}:{uid}:voice:{self.call_id}"

    @property
    def session_key(self) -> str:
        # Same disambiguation key openclaw uses internally for chat sessions.
        return f"agent:{self.agent_id}:openai-user:{self.user_field}"

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def append_tool_result(
        self, tool_name: str, args: dict[str, Any], result: str
    ) -> None:
        """Append a synthetic tool-result turn to the conversation history.

        Since the model is emitting tool calls as text content (not the
        structured ``tool_calls`` field), we can't use OpenAI's official
        tool-result message shape. Instead we append a user-style message
        that tells the model what happened, so the next iteration can
        produce a natural-language response.
        """
        # Truncate large tool outputs so we don't blow the context window.
        truncated = result if len(result) <= 4000 else result[:4000] + "... [truncated]"
        args_summary = (
            json.dumps(args, separators=(",", ":"))[:200] if args else "{}"
        )
        self.messages.append(
            {
                "role": "user",
                "content": (
                    f"[Tool result for {tool_name}({args_summary})]: {truncated}\n"
                    "Now respond to the user in a single short natural-language "
                    "sentence. Do NOT call any more tools."
                ),
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tool-call parsing
# ─────────────────────────────────────────────────────────────────────────────


_XML_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(?P<json>\{.*?\})\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
_FUNCTION_CALL_START_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*\{")


def _extract_tool_calls(text: str) -> list[dict[str, Any]]:
    """Find tool calls embedded in the model's text reply.

    Returns a list of ``{"name": str, "args": dict}`` entries. Empty list
    if the reply contains only natural language.

    Two formats handled:

    1. ``<tool_call>{"name": "x", "arguments": {...}}</tool_call>``
       — Mistral / some OSS models wrap the call in XML tags.

    2. ``identifier({...})``
       — Mistral large's bare function-call syntax (``task_create({...})``).
       Identifier matched as ``[a-zA-Z_][a-zA-Z0-9_]*``, JSON args extracted
       by brace-balancing.
    """
    if not text:
        return []
    calls: list[dict[str, Any]] = []

    # Format 1: XML-tagged
    for match in _XML_TOOL_CALL_RE.finditer(text):
        try:
            data = json.loads(match.group("json"))
        except json.JSONDecodeError:
            continue
        name = data.get("name") or data.get("tool")
        # Mistral uses "arguments", OpenAI uses "arguments" too.
        args = data.get("arguments") or data.get("args") or {}
        if isinstance(name, str) and name and isinstance(args, dict):
            calls.append({"name": name, "args": args})

    # Format 2: function-call syntax — find each `name({` and balance the JSON.
    i = 0
    while i < len(text):
        m = _FUNCTION_CALL_START_RE.search(text, i)
        if not m:
            break
        name = m.group(1)
        # Don't match common English words that look like identifiers followed
        # by parens. The "{" right after "(" is what makes function-call
        # detection reliable.
        json_start = m.end() - 1  # position of the opening "{"
        depth = 1
        j = json_start + 1
        in_string = False
        escape = False
        while j < len(text) and depth > 0:
            ch = text[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            j += 1
        if depth != 0:
            # Malformed; skip past this match
            i = m.end()
            continue
        json_str = text[json_start:j]
        try:
            args = json.loads(json_str)
        except json.JSONDecodeError:
            i = j
            continue
        if isinstance(args, dict):
            calls.append({"name": name, "args": args})
        i = j  # advance past the parsed call

    return calls


# ─────────────────────────────────────────────────────────────────────────────
# openclaw HTTP client (chat.completions + tools.invoke)
# ─────────────────────────────────────────────────────────────────────────────


def _gateway_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.OPENCLAW_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {settings.OPENCLAW_GATEWAY_TOKEN}"
    return headers


async def _call_chat_completions(
    session: VoiceAgentSession,
    *,
    timeout_s: float,
) -> str:
    """One round-trip to openclaw's /v1/chat/completions endpoint.

    Returns the raw assistant content (may contain tool-call markup).
    Raises on timeout or transport error so the caller can decide whether
    to retry or fall back.
    """
    messages: list[dict] = []
    if session.system_prompt:
        messages.append({"role": "system", "content": session.system_prompt})
    messages.extend(session.messages)

    # Model selection. The body `model` field MUST be the openclaw
    # agent alias form (`openclaw/<agentId>` or `openclaw`) — the
    # gateway rejects plain provider strings at the API layer:
    #
    #     {"error":{"message":"Invalid `model`. Use `openclaw` or
    #      `openclaw/<agentId>`.","type":"invalid_request_error"}}
    #
    # To override the model openclaw actually routes to, set the
    # ``x-openclaw-model`` header to a provider/model string (e.g.
    # "google/gemini-2.5-flash"). The header is honored by
    # ``resolveOpenAiCompatModelOverride`` in the openclaw gateway
    # and validated against the agent's allowed-models set from
    # openclaw.json — the chosen model must appear in
    # ``agents.defaults.models`` (or the per-agent allowed list).
    # Invalid models return a 400 with "Model 'X' is not allowed
    # for agent 'Y'."
    body = {
        "model": f"openclaw:{session.agent_id}",
        "messages": messages,
        "stream": False,
        "user": session.user_field,
        # tools=[] tells openclaw the caller is not registering ad-hoc tools.
        # The agent's own registered tools (via agent-manager extension) are
        # still available — openclaw injects them based on agent_id.
        "tools": [],
        "tool_choice": "none",
    }

    headers = {
        **_gateway_headers(),
        "x-openclaw-agent-id": session.agent_id,
    }

    # Voice-call model override. When ``settings.VOICE_CALL_CHAT_MODEL``
    # is set, we pass it through the ``x-openclaw-model`` header — this
    # is the openclaw-gateway-sanctioned way to route a single request
    # to a different provider/model while keeping agent resolution,
    # session tracking, billing, and logging wired up normally.
    # The model must be present in ``agents.defaults.models`` (or the
    # per-agent allowed list) in openclaw.json, otherwise the gateway
    # returns 400 "Model 'X' is not allowed for agent 'Y'."
    if settings.VOICE_CALL_CHAT_MODEL:
        headers["x-openclaw-model"] = settings.VOICE_CALL_CHAT_MODEL

    url = f"{settings.OPENCLAW_GATEWAY_URL}/v1/chat/completions"
    timeout = httpx.Timeout(connect=10.0, read=timeout_s, write=10.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code != 200:
        raise httpx.HTTPStatusError(
            f"openclaw chat.completions HTTP {resp.status_code}: {resp.text[:300]}",
            request=resp.request,
            response=resp,
        )

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()


async def _execute_tool(
    *,
    name: str,
    args: dict[str, Any],
    session: VoiceAgentSession,
) -> str:
    """Invoke an openclaw tool by name + args via the /tools/invoke endpoint.

    Returns the tool's result rendered as a string. On failure (HTTP error,
    tool not found, validation error, exception inside the tool) returns an
    error string starting with ``error:`` so the model can recover.
    """
    body = {
        "tool": name,
        "args": args,
        "sessionKey": session.session_key,
    }
    url = f"{settings.OPENCLAW_GATEWAY_URL}/tools/invoke"
    timeout = httpx.Timeout(
        connect=10.0, read=TOOLS_INVOKE_TIMEOUT_S, write=10.0, pool=10.0
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json=body,
                headers={
                    **_gateway_headers(),
                    "x-openclaw-agent-id": session.agent_id,
                },
            )
    except httpx.TransportError as exc:
        logger.warning(
            "tools.invoke transport error for call=%s tool=%s: %s",
            session.call_id,
            name,
            exc,
        )
        return f"error: cannot reach gateway: {exc}"
    except httpx.TimeoutException:
        logger.warning(
            "tools.invoke timed out for call=%s tool=%s", session.call_id, name
        )
        return "error: tool execution timed out"

    if resp.status_code == 404:
        return f"error: tool '{name}' not available for this agent"
    if resp.status_code >= 400:
        try:
            payload = resp.json()
            err = (payload.get("error") or {}).get("message") or resp.text
        except Exception:
            err = resp.text
        return f"error: {err[:300]}"

    try:
        payload = resp.json()
    except Exception:
        return f"error: invalid JSON from /tools/invoke: {resp.text[:200]}"

    if not payload.get("ok"):
        err = (payload.get("error") or {}).get("message") or "unknown tool error"
        return f"error: {err[:300]}"

    result = payload.get("result")
    return _render_tool_result(result)


def _render_tool_result(result: Any) -> str:
    """Convert a tool's structured result into a readable string for the model.

    openclaw tools typically return ``{"content": [{"type": "text", "text": "..."}], ...}``
    (Anthropic-style content blocks). We extract the text and return it.
    Other shapes are JSON-stringified.
    """
    if result is None:
        return "(no result)"
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            if parts:
                return "\n".join(parts)
        # Fall through to JSON dump
    try:
        return json.dumps(result, default=str, separators=(",", ":"))[:4000]
    except Exception:
        return str(result)[:4000]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def run_agent_turn(
    session: VoiceAgentSession,
    user_text: str,
    *,
    timeout_s: float = DEFAULT_AGENT_TIMEOUT_S,
) -> str:
    """Send the user's latest utterance and return the agent's natural reply.

    Runs the inner loop:
        chat → parse tool calls → execute → loop until natural language.

    Returns a string suitable to speak via TTS — never raw tool-call markup
    or JSON. On unrecoverable errors, returns a short fallback sentence so
    the caller isn't left in silence.
    """
    session.append_user(user_text)

    last_reply = ""
    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            reply = await _call_chat_completions(session, timeout_s=timeout_s)
        except httpx.ConnectError as exc:
            logger.error(
                "Agent bridge: cannot reach openclaw gateway at %s: %s",
                settings.OPENCLAW_GATEWAY_URL,
                exc,
            )
            return _fallback_reply(
                "I lost connection to my systems. Please try again in a moment."
            )
        except httpx.TimeoutException:
            logger.warning(
                "Agent bridge: agent turn timed out for call %s (iteration %d)",
                session.call_id,
                iteration,
            )
            return _fallback_reply(
                "Sorry, I'm taking longer than usual. Could you say that again?"
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Agent bridge: gateway returned non-200 for call %s: %s",
                session.call_id,
                exc,
            )
            return _fallback_reply(
                "I had trouble reaching my brain just now. Can you repeat that?"
            )
        except Exception as exc:
            logger.exception(
                "Agent bridge: unexpected error during turn for call %s: %s",
                session.call_id,
                exc,
            )
            return _fallback_reply("I hit a snag. Let me try again.")

        last_reply = reply

        if not reply:
            logger.warning(
                "Agent bridge: empty reply from agent for call %s (iteration %d)",
                session.call_id,
                iteration,
            )
            return _fallback_reply("Sorry, I didn't catch that. Can you try again?")

        tool_calls = _extract_tool_calls(reply)
        if not tool_calls:
            # Natural language reply — done.
            session.append_assistant(reply)
            return reply

        # The model called one or more tools. Execute them, append results to
        # history, and loop. We persist the assistant's tool-call turn first
        # so the next iteration sees the same conversation state the model
        # just produced.
        session.append_assistant(reply)
        logger.info(
            "Call %s: agent invoked %d tool(s) on iteration %d: %s",
            session.call_id,
            len(tool_calls),
            iteration,
            ", ".join(tc["name"] for tc in tool_calls),
        )
        for tc in tool_calls:
            result = await _execute_tool(
                name=tc["name"], args=tc["args"], session=session
            )
            session.append_tool_result(tc["name"], tc["args"], result)
            logger.info(
                "Call %s: tool %s → %r",
                session.call_id,
                tc["name"],
                result[:200],
            )

    # Hit max iterations. The model is stuck in a tool loop — return whatever
    # it last said and let the caller fall back.
    logger.warning(
        "Agent bridge: hit MAX_TOOL_ITERATIONS=%d for call %s; returning last reply",
        MAX_TOOL_ITERATIONS,
        session.call_id,
    )
    return last_reply or _fallback_reply(
        "I'm having trouble completing that. Let me try a different approach."
    )


def _fallback_reply(text: str) -> str:
    """Placeholder we say aloud on errors so the caller isn't left in silence."""
    return text
