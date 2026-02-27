---
name: cron-manager
description: Manage all scheduled/recurring tasks through this API instead of using the built-in cron system directly. This ensures every cron job you create is visible in the user's dashboard UI. Always use these endpoints — never bypass them.
trigger: "cron|schedule|recurring|timer|interval|periodic|every|repeat|automate|scheduled task"
tools: [shell]
metadata: {"openclaw": {"requires": {"bins": ["curl", "jq"]}}}
---

# Cron Manager

Internal API: http://localhost:8000/api
Public Base: https://openclaw.marketsverse.com/api

## ⚠️ CRITICAL RULE

**NEVER use the built-in OpenClaw cron system directly** (e.g. `openclaw cron add`).
**ALWAYS use these HTTP endpoints** to create, update, and delete cron jobs.

This is **mandatory** because:
- Jobs created through the API are tracked in the database with ownership (user_id, session_id)
- They become visible in the user's dashboard UI
- Jobs created directly via CLI bypass the ownership layer and appear as orphaned entries

If you need to schedule anything — emails, reports, checks, reminders — use this skill.

---

## Your Identity
Your agent_id is your agent name in lowercase (e.g. aura, nexus, main).
```bash
grep -i "agent id" ~/IDENTITY.md | awk -F: '{print $2}' | tr -d ' '

```

---

## CREATE A CRON JOB

Schedule types:
- `every` — repeats at a fixed interval using human-readable duration (e.g. `3m` = 3 minutes, `1h` = 1 hour, `1d` = 1 day)
- `cron` — standard cron expression (e.g. `0 9 * * *` = daily at 9 AM)
- `at` — one-time execution at a specific ISO timestamp

```bash
curl -s -X POST "http://localhost:8000/api/crons" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Human-readable job name",
    "agent_id": "YOUR_ID",
    "schedule_kind": "every",
    "schedule_expr": "5m",
    "schedule_human": "Every 5 minutes",
    "session_target": "isolated",
    "payload_message": "The primary prompt the agent will execute",
    "pipeline_template": {
      "tasks": [
        { "name": "Fetch Data", "description": "Get latest news", "status": "pending", "integrations": [], "context_sources": [] }
      ],
      "global_integrations": [],
      "global_context_sources": []
    },
    "delivery_mode": "webhook",
    "enabled": true,
    "delete_after_run": false,
    "user_id": "USER_ID",
    "session_id": "SESSION_ID"
  }' | jq .

```

**Parameters:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Display name shown in UI |
| `agent_id` | ✅ | Which agent runs this job |
| `schedule_kind` | ✅ | `every`, `cron`, or `at` |
| `schedule_expr` | ✅ | Duration string (e.g. `3m`, `1h`, `1d`), cron expr, or ISO timestamp |
| `schedule_tz` | ❌ | IANA timezone (only for `cron` kind, e.g. `Asia/Kolkata`) |
| `schedule_human`| ❌ | Human readable schedule string (e.g. "Every Monday at 9AM") |
| `session_target` | ❌ | `isolated` (default) or `main` |
| `payload_message` | ✅ | The base prompt the agent receives each run |
| `pipeline_template`| ❌ | JSON object defining structured tasks (agent will return status for each task) |
| `delivery_mode` | ❌ | `webhook` (default) or `none` |
| `enabled` | ❌ | `true` (default) or `false` |
| `delete_after_run` | ❌ | `true` to auto-delete after first run (for `at` jobs) |
| `user_id` | ✅ | Owner user ID — required for dashboard visibility |
| `session_id` | ✅ | Owner session ID — required for dashboard visibility |

Save the returned `job_id` — you need it for updates and deletion.

---

## LIST CRON JOBS

```bash
# All jobs (optionally filter by user_id / session_id)
curl -s "http://localhost:8000/api/crons" | jq .

# Filter by owner
curl -s "http://localhost:8000/api/crons?user_id=USER_ID&session_id=SESSION_ID" | jq .

```

---

## GET A SINGLE CRON JOB

```bash
curl -s "http://localhost:8000/api/crons/JOB_ID" | jq .

```

---

## UPDATE A CRON JOB

Only send the fields you want to change.

```bash
curl -s -X PATCH "http://localhost:8000/api/crons/JOB_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_kind": "every",
    "schedule_expr": "10m",
    "payload_message": "Updated prompt for the agent",
    "enabled": true
  }' | jq .

```

---

## DELETE A CRON JOB

```bash
curl -s -X DELETE "http://localhost:8000/api/crons/JOB_ID" | jq .

```

---

## TRIGGER A JOB IMMEDIATELY

Run a job right now without waiting for its next scheduled time:

```bash
curl -s -X POST "http://localhost:8000/api/crons/JOB_ID/trigger" | jq .

```

---

## VIEW RUN HISTORY

See the last N executions of a job:

```bash
curl -s "http://localhost:8000/api/crons/JOB_ID/runs?limit=10" | jq .

```

---

## Common Schedule Examples

| Goal | Kind | Expression |
|------|------|------------|
| Every 5 minutes | `every` | `5m` |
| Every hour | `every` | `1h` |
| Every day at 9 AM IST | `cron` | `0 9 * * *` (tz: `Asia/Kolkata`) |
| Every Monday at 10 AM | `cron` | `0 10 * * 1` |
| Once at a specific time | `at` | `2026-03-01T09:00:00Z` |

---

## Best Practices

* **Always use this API** — never use `openclaw cron add` directly. The UI depends on it.
* **Provide user_id and session_id** — without them, jobs won't show in the user's dashboard.
* **Use descriptive names** — the name appears in the UI, make it meaningful.
* **Use isolated sessions** — set `session_target` to `isolated` unless you need to share state with the main conversation.
* **Craft clear payload messages** — the `payload_message` is the exact prompt the agent receives, so be specific.
* **Check run history** — before modifying a job, check its run history to understand its behavior.
* **Production:** In remote environments, use the Public Base URL.
