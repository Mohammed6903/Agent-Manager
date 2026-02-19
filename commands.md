## 1. Create Agent Filesystem

```bash
mkdir -p /root/.openclaw/workspace-<agentid>
mkdir -p /root/.openclaw/agents/<agentid>/agent

cat > /root/.openclaw/workspace-<agentid>/IDENTITY.md << 'EOF'
# Identity
Name: <Name>
Agent ID: <agentid>
Role: <Role>
EOF

cat > /root/.openclaw/workspace-<agentid>/SOUL.md << 'EOF'
# <Name>
You are <Name>. <Personality description>
Your agent ID is <agentid>. Always use it exactly when calling tools.
EOF
```

---

## 2. Register Agent in Gateway

```bash
# Step 1 — get current config hash
HASH=$(openclaw gateway call config.get --params '{}' --json | jq -r '.hash')

# Step 2 — verify hash is set
echo "Hash: $HASH"

# Step 3 — patch config
openclaw gateway call config.patch --params "{
  \"baseHash\": \"$HASH\",
  \"raw\": \"{ agents: { list: [{ id: \\\"<agentid>\\\", name: \\\"<Name>\\\", workspace: \\\"/root/.openclaw/workspace-<agentid>\\\", agentDir: \\\"/root/.openclaw/agents/<agentid>/agent\\\" }] } }\"
}" --json
```

Expected response: `"ok": true`

---

## 3. Verify Agent Is Registered

```bash
openclaw agents list --json
```

---

## 4. Test Chat (non-streaming)

```bash
curl -s -X POST http://localhost:18789/v1/chat/completions \
  -H "Authorization: Bearer <your_gateway_token>" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-agent-id: <agentid>" \
  -d '{
    "model": "openclaw:<agentid>",
    "messages": [{"role": "user", "content": "say hello and tell me your agent ID"}],
    "stream": false,
    "user": "<agentid>:<userid>"
  }' | jq .
```

---

## 5. Test Chat (streaming)

```bash
curl -s -X POST http://localhost:18789/v1/chat/completions \
  -H "Authorization: Bearer <your_gateway_token>" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-agent-id: <agentid>" \
  -d '{
    "model": "openclaw:<agentid>",
    "messages": [{"role": "user", "content": "say hello"}],
    "stream": true,
    "user": "<agentid>:<userid>"
  }'
```

---

## 6. Test Session Persistence

```bash
# First message — plant a fact
curl -s -X POST http://localhost:18789/v1/chat/completions \
  -H "Authorization: Bearer <your_gateway_token>" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-agent-id: <agentid>" \
  -d '{
    "model": "openclaw:<agentid>",
    "messages": [{"role": "user", "content": "my favourite color is purple, remember that"}],
    "stream": false,
    "user": "<agentid>:<userid>"
  }' | jq .

# Second message — same user field, should remember
curl -s -X POST http://localhost:18789/v1/chat/completions \
  -H "Authorization: Bearer <your_gateway_token>" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-agent-id: <agentid>" \
  -d '{
    "model": "openclaw:<agentid>",
    "messages": [{"role": "user", "content": "what is my favourite color?"}],
    "stream": false,
    "user": "<agentid>:<userid>"
  }' | jq .
```

---

## 7. Start a New Session (same user)

Change the `user` field — no commands needed, just a different value:

```
"user": "<agentid>:<userid>"           ← persistent session
"user": "<agentid>:<userid>:<timestamp>" ← new session
```

For a programmatic new session from your server:
```python
import time
session_user = f"{agent_id}:{user_id}:{int(time.time())}"
```

---

## 8. Full Memory Reset (clears both session + MEMORY.md)

```bash
# Clear persistent memory
echo "" > /root/.openclaw/workspace-<agentid>/MEMORY.md

# Use a new user field value to also get a fresh session transcript
# (just change the user field in your next request)
```

---

## 9. Inspect Sessions

```bash
# All sessions across all agents
openclaw sessions --json

# Sessions for a specific agent
openclaw sessions --agent <agentid> --json

# Raw session files on disk
cat /root/.openclaw/agents/<agentid>/sessions/sessions.json | jq .
ls /root/.openclaw/agents/<agentid>/sessions/*.jsonl
```

---

## 10. Update Agent Identity

```bash
# Edit SOUL.md or IDENTITY.md directly
cat > /root/.openclaw/workspace-<agentid>/SOUL.md << 'EOF'
# <Name> v2
Updated personality here...
EOF

# Changes take effect on the NEXT new session automatically
# No gateway restart needed
```

---

## 11. Delete Agent

```bash
# Step 1 — remove from Gateway config (interactive, pipe y)
openclaw agents delete <agentid> --json --force

# Step 2 — clean up filesystem (not handled by delete command)
rm -rf /root/.openclaw/workspace-<agentid>
rm -rf /root/.openclaw/agents/<agentid>
```

---

## Summary of Confirmed Behaviors

| Operation | How | Verified |
|---|---|---|
| Create | `config.patch` with `baseHash` | ✓ |
| List | `openclaw agents list --json` | ✓ |
| Chat | `/v1/chat/completions` | ✓ |
| Session persistence | Same `user` field | ✓ |
| New session | Different `user` field | ✓ |
| Memory reset | Truncate `MEMORY.md` | ✓ |
| Delete config | `echo "y" \| openclaw agents delete` | ✓ |
| Delete filesystem | `rm -rf` workspace + agents dir | ✓ |
| `--yes` flag | Does NOT exist in this build, use --force | ✓ |
| `env` in agents.list | Does NOT exist in this build | ✓ |
