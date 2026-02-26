---
name: workspace-bridge
description: Use for any Gmail, Calendar, or Notion task — manage emails (send, reply, search), calendar events, and Notion pages/databases. Handles secure secret storage for external integrations.
trigger: "email|gmail|notion|calendar|event|schedule|page|database|send email|reply email|read email|search email|thread|attachment|label|archive|mark read|star|create page|search notion|connect gmail|secrets"
tools: [shell]
metadata: {"openclaw": {"requires": {"bins": ["curl", "jq"]}}}
---

# Workspace Bridge

Internal API: http://localhost:8000/api/gmail
Public Base: https://openclaw.marketsverse.com/api/gmail

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
curl -s "http://localhost:8000/api/gmail/auth/login?agent_id=YOUR_ID" | jq -r '.auth_url'

```

Show the returned URL to the user as: "Please open this link to authorize Gmail: <url>"
Wait for confirmation before retrying. Do NOT proceed until they confirm.

---

## GMAIL — READING

### List/Search emails

```bash
curl -s "http://localhost:8000/api/gmail/email/list?agent_id=YOUR_ID&max_results=10&query=QUERY" | jq .

```

### Read email or thread

```bash
curl -s "http://localhost:8000/api/gmail/email/read?agent_id=YOUR_ID&message_id=MESSAGE_ID" | jq .
curl -s "http://localhost:8000/api/gmail/email/thread?agent_id=YOUR_ID&thread_id=THREAD_ID" | jq .

```

### Batch Read (multiple IDs)

```bash
curl -s -X POST "http://localhost:8000/api/gmail/email/batch_read" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "YOUR_ID", "message_ids": ["ID1", "ID2"]}' | jq .

```

---

## GMAIL — SENDING

### Send or Reply

```bash
# For new emails
curl -s -X POST "http://localhost:8000/api/gmail/email/send" \
  -H "Content-Type: application/json" \
  -d '{ "agent_id": "YOUR_ID", "to": "recipient@example.com", "subject": "SUB", "body": "BODY" }' | jq .

# For replies (preserves thread)
curl -s -X POST "http://localhost:8000/api/gmail/email/reply" \
  -H "Content-Type: application/json" \
  -d '{ "agent_id": "YOUR_ID", "message_id": "ORIGINAL_ID", "body": "REPLY_TEXT" }' | jq .

```

---

## CALENDAR

### List or Create Events

```bash
# List
curl -s "http://localhost:8000/api/gmail/calendar/events?agent_id=YOUR_ID&max_results=5" | jq .

# Create
curl -s -X POST "http://localhost:8000/api/gmail/calendar/events" \
  -H "Content-Type: application/json" \
  -d '{ "agent_id": "YOUR_ID", "summary": "TITLE", "start_time": "YYYY-MM-DDTHH:MM:SS", "end_time": "YYYY-MM-DDTHH:MM:SS" }' | jq .

```

---

## SECRETS & NOTION

### Manage Secrets

```bash
# Store
curl -s -X POST "http://localhost:8000/api/gmail/secrets" \
  -H "Content-Type: application/json" \
  -d '{ "agent_id": "YOUR_ID", "service_name": "notion", "secret_data": {"api_key": "ntn_..."} }' | jq .

# Retrieve Key
NOTION_KEY=$(curl -s "http://localhost:8000/api/gmail/secrets/YOUR_ID/notion" | jq -r '.secret_data.api_key')

```

### Notion Actions (Direct API)

```bash
curl -s -X POST "[https://api.notion.com/v1/search](https://api.notion.com/v1/search)" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"query": "QUERY"}' | jq .

```

---

## Error Handling & Best Practices

* **401 (Unauthorized):** Trigger Gmail Auth flow immediately.
* **404 (Secrets):** Key missing; request Notion token from user and store via secrets endpoint.
* **500 (Server Error):** Verbatim report the `detail` field to the user.
* **Confirmations:** Never send/reply to email or modify calendar/Notion without explicit user approval.
* **Production:** In remote environments, use the Public Base URL.