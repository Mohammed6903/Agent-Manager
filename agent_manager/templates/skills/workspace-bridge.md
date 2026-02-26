---
name: workspace-bridge
description: Use for any Gmail or Notion task — send email, reply, read inbox, search emails, manage labels, read threads, download attachments, connect Gmail, store or retrieve secrets, manage Notion pages and databases.
trigger: "email|gmail|notion|page|database|send email|reply email|read email|search email|thread|attachment|label|archive|mark read|star|create page|search notion|connect gmail|secrets"
tools: [shell]
metadata: {"openclaw": {"requires": {"bins": ["curl", "jq"]}}}
---

# Workspace Bridge

Internal API: http://localhost:8000/gmail-auth
Public Base: https://openclaw.marketsverse.com/gmail-auth

## Your Identity
Your agent_id is your agent name in lowercase (e.g. aura, nexus, main).
Read it from your IDENTITY.md if unsure:
```bash
grep -i "agent id" ~/IDENTITY.md | awk -F: '{print $2}' | tr -d ' '
```
Always use it exactly as-is. Never modify or guess it.

---

## GMAIL AUTH

### Connect Gmail (first time or after 401)
```bash
curl -s "http://localhost:8000/auth/login?agent_id=YOUR_ID" | jq -r '.auth_url'
```
Show the returned URL to the user as: "Please open this link to authorize Gmail: <url>"
Wait for confirmation before retrying. Do NOT proceed until they confirm.

### Manual callback (if user pastes just the code)
```bash
curl -s -X POST "http://localhost:8000/auth/callback/manual" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "YOUR_ID", "code": "AUTH_CODE"}' | jq .
```

---

## GMAIL — READING

### List recent emails
```bash
curl -s "http://localhost:8000/email/list?agent_id=YOUR_ID&max_results=10" | jq .
```

### Search emails (Gmail query syntax)
```bash
curl -s "http://localhost:8000/email/search?agent_id=YOUR_ID&query=QUERY&max_results=10" | jq .
```

### Read a full email
```bash
curl -s "http://localhost:8000/email/read?agent_id=YOUR_ID&message_id=MESSAGE_ID" | jq .
```

### Read multiple emails at once
```bash
curl -s -X POST "http://localhost:8000/email/batch_read" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "YOUR_ID", "message_ids": ["ID1", "ID2"]}' | jq .
```

---

## GMAIL — SENDING

### Send a new email
Always confirm recipient, subject, and body with user before sending.
```bash
curl -s -X POST "http://localhost:8000/email/send" \
  -H "Content-Type: application/json" \
  -d '{ "agent_id": "YOUR_ID", "to": "recipient@example.com", "subject": "SUBJECT", "body": "BODY" }' | jq .
```

### Reply to an email (preserves thread)
```bash
curl -s -X POST "http://localhost:8000/email/reply" \
  -H "Content-Type: application/json" \
  -d '{ "agent_id": "YOUR_ID", "message_id": "MESSAGE_ID", "body": "REPLY_BODY" }' | jq .
```

---

## SECRETS

### Store or update a secret
```bash
curl -s -X POST "http://localhost:8000/secrets" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "YOUR_ID",
    "service_name": "SERVICE",
    "secret_data": {"key": "VALUE"}
  }' | jq .
```

### Retrieve a secret
```bash
curl -s "http://localhost:8000/secrets/YOUR_ID/SERVICE_NAME" | jq .
```

### List all secrets for an agent
```bash
curl -s "http://localhost:8000/secrets/YOUR_ID" | jq .
```

### Delete a secret
```bash
curl -s -X DELETE "http://localhost:8000/secrets/YOUR_ID/SERVICE_NAME" | jq .
```

---

## NOTION

### Step 0 — Fetch your Notion key
```bash
NOTION_KEY=$(curl -s "http://localhost:8000/secrets/YOUR_ID/notion" \
  | jq -r '.secret_data.api_key')
```

### Search workspace
```bash
curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"query": "QUERY"}' | jq .
```

---

## Error Handling & Best Practices
- 401 on Gmail → run Gmail connect flow, wait for confirmation, retry.
- 404 on secrets → key not stored yet; ask user to provide it, store it, retry.
- 401 on Notion → key invalid or integration not shared with the target page/database.
- 500 anywhere → report the `detail` field verbatim to the user.
- Never send or reply to email without explicit user confirmation.
