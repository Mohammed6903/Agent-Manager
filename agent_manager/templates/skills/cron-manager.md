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

---

## ⚠️ CRITICAL RULE — READ THIS FIRST

**NEVER use the built-in OpenClaw cron system directly** (e.g. `openclaw cron add`).
**ALWAYS use these HTTP endpoints** to create, update, and delete cron jobs.

This is **mandatory** because:
- Jobs created through the API are tracked in the database with ownership (user_id, session_id)
- They become visible in the user's dashboard UI
- Jobs created directly via CLI bypass the ownership layer and appear as orphaned entries

---

## ⚠️ MANDATORY: PLAN BEFORE YOU CREATE

**Before calling the cron creation endpoint, you MUST complete a full planning phase.**

Do NOT create a cron job until you have answered all of the following:

### Step 1 — Understand what the user actually wants
- What is the end goal? (e.g. "add LinkedIn job links to a Notion page")
- What triggers it? (schedule, frequency, timezone)
- What does success look like in the real world? (e.g. "a new section appears on the Notion page with the job links")

### Step 2 — Identify every integration required
For each integration (Notion, Gmail, Slack, etc.), you MUST determine:
- What exact API endpoint will be called? (full URL, HTTP method, path params)
- What request headers are required? (Auth format, API version headers, content type)
- What request body shape does it expect? (exact field names and types)
- What does a successful response look like? (which field confirms the action was performed?)
- What could fail and how will the task handle it?

Do this by consulting your knowledge of the API, calling workspace-bridge to discover credentials, or checking OpenAPI docs if available. **You must know the answer to all of the above before writing the pipeline_template.**

### Step 3 — Break the goal into atomic pipeline tasks
Each task must:
- Do exactly one thing (fetch credentials, call one API, verify one result)
- Specify the exact API call it will make (endpoint, method, body shape)
- Define what "success" means for that specific call (which response field to check)
- Define what happens if a prior task failed (skip and mark error, or continue)

### Step 4 — Write the payload_message with full operational detail
The `payload_message` is the exact prompt the executing agent receives. It must be so detailed that the agent cannot misinterpret it. Include:
- The exact sequence of steps
- The exact API endpoints (full URL, HTTP method, headers, body shape) for each step
- The exact field in each API response that confirms success
- What to do on failure at each step
- The explicit instruction: **"Do NOT mark a task as success unless the API response contains the confirmation field specified. If the field is absent or the response is an error, mark the task as error and include the exact response."**

### Step 5 — Only then, call the cron creation endpoint

---

## ⚠️ pipeline_template IS MANDATORY

**Every cron job MUST include a `pipeline_template`. There are no exceptions.**

A job without a `pipeline_template` will not provide structured results, per-task status tracking, or reliable webhook data. Even the simplest single-step job must have a template with at least one task.

The `description` field of each task must be operational — it must contain the exact API call, body shape, and success criterion. Not "update Notion" but:

> "PATCH https://api.notion.com/v1/blocks/{page_id}/children with Authorization: Bearer {notion_token} and Notion-Version: 2022-06-28. Body: children array of bulleted_list_item blocks. Success = response.results array where every entry has an 'id' field."

---

## ⚠️ SESSION TARGET: CRITICAL FOR INTEGRATIONS

**`session_target` controls whether your integrations (Gmail, Notion, etc.) are available.**

| Value | Has Integrations? | Use When |
|-------|-------------------|----------|
| `main` | ✅ Yes — full access to all configured tools | Job needs Gmail, Notion, or ANY external integration |
| `isolated` | ❌ No — blank slate, no tools | Job is purely self-contained, no external APIs |

**Always set `session_target: "main"` when your pipeline uses any external integration.**
When using `main`, the payload kind is automatically set to `systemEvent` by the server.

---

## ⚠️ PIPELINE VALIDATION REQUIREMENT

When any task calls an external API, you **MUST**:

- Only mark the task `"success"` if the API response contains the **specific confirmation field** defined during planning
- If the response is an error, a 4xx/5xx, or the confirmation field is absent → mark `"error"` with the exact response body
- **Never treat "I sent the request" as success** — only a confirmed real-world side effect counts

### Notion validation:
- `PATCH https://api.notion.com/v1/blocks/{block_id}/children` → success only if response contains `results` array where each entry has an `"id"` field
- `POST https://api.notion.com/v1/pages` → success only if response contains `"id"` and `"object": "page"`
- `PATCH https://api.notion.com/v1/pages/{page_id}` → success only if response contains `"id"` matching the patched page

### Gmail validation:
- Remove UNREAD label: `POST https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}/modify` with `{"removeLabelIds": ["UNREAD"]}` → success only if response `labelIds` does NOT contain `"UNREAD"`
- Send email: success only if response contains `"id"` and `"threadId"`
- List/search messages: success if response contains `"messages"` array (empty array is valid — means no matching emails)

### For dependent tasks:
- If Task B depends on Task A and Task A failed → Task B must be marked `"error"` with `"error": "Skipped: prior task '<Task A name>' failed"`

---

## ⚠️ WORKSPACE-BRIDGE: CREDENTIAL STORE, NOT PROXY

Workspace-bridge is a **credential store** — use it to fetch API keys and secrets only.
Once you have the credentials, call the **official 3rd-party API directly**.

**Correct pattern:**
1. Call workspace-bridge to retrieve the Notion integration token or Gmail OAuth credentials
2. Use those credentials to call `https://api.notion.com/v1/...` or Gmail API directly
3. Verify the response confirms the real-world effect

**Wrong pattern:** Calling URLs like `/api/notion/page/append` or `/api/workspace-bridge/notion/...` as proxies — these will 404. Workspace-bridge only provides credentials, not API proxying.

---

## Your Identity

Your agent_id is your agent name in lowercase (e.g. aura, nexus, main).

```bash
grep -i "agent id" ~/IDENTITY.md | awk -F: '{print $2}' | tr -d ' '
```

---

## CREATE A CRON JOB

Schedule types:
- `every` — repeats at a fixed interval using human-readable duration (e.g. `3m`, `1h`, `1d`)
- `cron` — standard cron expression (e.g. `0 9 * * *` = daily at 9 AM)
- `at` — one-time execution at a specific ISO timestamp

```bash
curl -s -X POST "http://localhost:8000/api/crons" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Human-readable job name",
    "agent_id": "YOUR_AGENT_ID",
    "schedule_kind": "every",
    "schedule_expr": "5m",
    "schedule_human": "Every 5 minutes",
    "session_target": "main",
    "payload_message": "FULL DETAILED OPERATIONAL PROMPT — see Payload Message Guidance below",
    "pipeline_template": {
      "tasks": [
        {
          "name": "Step name",
          "description": "Exact API call: METHOD https://api.example.com/endpoint. Headers: X. Body: {...}. Success = response contains field Y with value Z.",
          "status": "pending",
          "integrations": ["integration-name"],
          "context_sources": []
        }
      ],
      "global_integrations": ["integration-name"],
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
| `schedule_human` | ❌ | Human readable schedule string (e.g. "Every Monday at 9AM IST") |
| `session_target` | ❌ | `main` (has integrations) or `isolated` (no tools). Default: `main` |
| `payload_message` | ✅ | Full operational prompt — must include exact API calls, success criteria, error handling |
| `pipeline_template` | ✅ **MANDATORY** | Structured task definitions with exact API details per task |
| `delivery_mode` | ❌ | `webhook` (default) or `none` |
| `enabled` | ❌ | `true` (default) or `false` |
| `delete_after_run` | ❌ | `true` to auto-delete after first run (for `at` jobs) |
| `user_id` | ✅ | Owner user ID — required for dashboard visibility |
| `session_id` | ✅ | Owner session ID — required for dashboard visibility |

---

## PAYLOAD MESSAGE GUIDANCE

The `payload_message` is the exact prompt the executing agent receives every time the job runs. The agent has **no prior context** — treat it as a fresh agent that only knows what you put in this message.

**Every `payload_message` for an integration job must include:**

1. **The goal** — what real-world outcome is expected
2. **Step-by-step instructions** — in the exact order tasks must run
3. **For each step:** exact HTTP method, full URL, required headers, exact body shape, exact success confirmation field
4. **The validation rule** — explicitly state that tasks must not be marked success without the confirmation field
5. **The pipeline_result output reminder** — instruct the agent to output the structured block at the very end

### Example payload_message for a Notion + Gmail job:

```
You are executing a scheduled pipeline. Follow every step exactly and in order.

GOAL: Fetch the last 10 LinkedIn job emails from Gmail, extract job links, append them as a bulleted list to the Notion page "Job Tracker", then mark those emails as read.

STEP 1 — Fetch Notion credentials
  Call: GET http://localhost:8000/api/workspace-bridge/credentials?integration=notion
  Success: response.credentials.api_key is non-empty — store as notion_token
  On failure: mark task error, stop pipeline

STEP 2 — Fetch Gmail credentials
  Call: GET http://localhost:8000/api/workspace-bridge/credentials?integration=gmail
  Success: response.credentials.access_token is non-empty — store as gmail_token
  On failure: mark task error, stop pipeline

STEP 3 — Search LinkedIn job emails
  Call: GET https://gmail.googleapis.com/gmail/v1/users/me/messages?q=from:linkedin.com+subject:job&maxResults=10
  Headers: Authorization: Bearer {gmail_token}
  Success: response contains "messages" key (empty array is valid — means no new emails, mark success and skip steps 4-6)
  Extract: list of message id values

STEP 4 — Fetch each email body
  For each message id from Step 3:
    Call: GET https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}?format=full
    Headers: Authorization: Bearer {gmail_token}
    Extract: job title and application URL from body/snippet
  Success: at least one email fetched without HTTP error

STEP 5 — Append job links to Notion page
  Call: PATCH https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children
  Headers:
    Authorization: Bearer {notion_token}
    Notion-Version: 2022-06-28
    Content-Type: application/json
  Body:
    { "children": [ { "object": "block", "type": "bulleted_list_item", "bulleted_list_item": { "rich_text": [{"type": "text", "text": {"content": "{job_title}", "link": {"url": "{job_url}"}}}] } } ] }
  Success: response.results array is non-empty and every entry has an "id" field
  On failure: mark task error with exact response body

STEP 6 — Mark emails as read
  For each message id from Step 3:
    Call: POST https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}/modify
    Headers: Authorization: Bearer {gmail_token}
    Body: {"removeLabelIds": ["UNREAD"]}
    Success: response.labelIds does NOT contain "UNREAD"
  On failure for individual email: mark task error, continue to next

VALIDATION RULE: Do NOT mark any task as success unless the exact confirmation field specified above is present in the API response. If the field is absent, the HTTP status is 4xx/5xx, or the side effect cannot be verified, mark the task as error and include the full API response in the error field.

At the very end of your response, after completing all steps, output the pipeline_result block exactly as specified in your system instructions.
```

---

## PIPELINE TEMPLATE — CANONICAL EXAMPLES

### Integration pipeline (Notion + Gmail) — `session_target: "main"`

```json
{
  "tasks": [
    {
      "name": "Fetch Notion credentials",
      "description": "GET http://localhost:8000/api/workspace-bridge/credentials?integration=notion. Success = response.credentials.api_key is non-empty. Store as notion_token for subsequent steps.",
      "status": "pending",
      "integrations": ["workspace-bridge"],
      "context_sources": []
    },
    {
      "name": "Fetch Gmail credentials",
      "description": "GET http://localhost:8000/api/workspace-bridge/credentials?integration=gmail. Success = response.credentials.access_token is non-empty. Store as gmail_token.",
      "status": "pending",
      "integrations": ["workspace-bridge"],
      "context_sources": []
    },
    {
      "name": "Search LinkedIn job emails",
      "description": "GET https://gmail.googleapis.com/gmail/v1/users/me/messages?q=from:linkedin.com+subject:job&maxResults=10 with Authorization: Bearer {gmail_token}. Success = response contains 'messages' key. Empty array is valid.",
      "status": "pending",
      "integrations": ["gmail"],
      "context_sources": []
    },
    {
      "name": "Append jobs to Notion page",
      "description": "PATCH https://api.notion.com/v1/blocks/{PAGE_ID}/children with Authorization: Bearer {notion_token} and Notion-Version: 2022-06-28. Body: children array of bulleted_list_item blocks with job title and URL. Success = response.results array where every entry has an 'id' field.",
      "status": "pending",
      "integrations": ["notion"],
      "context_sources": []
    },
    {
      "name": "Mark emails as read",
      "description": "For each message id: POST https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}/modify with body {removeLabelIds: ['UNREAD']}. Success = response.labelIds does NOT contain 'UNREAD'. On failure for individual email, mark error and continue.",
      "status": "pending",
      "integrations": ["gmail"],
      "context_sources": []
    }
  ],
  "global_integrations": ["notion", "gmail"],
  "global_context_sources": ["workspace-bridge"]
}
```

### Self-contained pipeline — `session_target: "isolated"`

```json
{
  "tasks": [
    {
      "name": "Check system health",
      "description": "Run internal health checks using available tools and summarize results. Success = health check completes without exception.",
      "status": "pending",
      "integrations": [],
      "context_sources": []
    }
  ],
  "global_integrations": [],
  "global_context_sources": []
}
```

---

## LIST CRON JOBS

```bash
# All jobs
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
    "payload_message": "Updated prompt",
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

The API returns immediately — the job runs in the background and results arrive via webhook.

```bash
curl -s -X POST "http://localhost:8000/api/crons/JOB_ID/trigger" | jq .
```

---

## VIEW RUN HISTORY

```bash
curl -s "http://localhost:8000/api/crons/JOB_ID/runs?limit=10" | jq .
```

---

## Common Schedule Examples

| Goal | Kind | Expression |
|------|------|------------|
| Every 5 minutes | `every` | `5m` |
| Every hour | `every` | `1h` |
| Every day at 9 AM IST | `cron` | `0 9 * * *` + `tz: Asia/Kolkata` |
| Every Monday at 10 AM | `cron` | `0 10 * * 1` |
| Once at a specific time | `at` | `2026-03-01T09:00:00Z` |

---

## Best Practices

- **Plan first, create second** — fully understand every API call, endpoint, and success criterion before writing the job
- **`pipeline_template` is mandatory** — every job must have one, no exceptions
- **Task descriptions must be operational** — include exact URL, method, body shape, and success field. Not "update Notion" but the full PATCH call with headers and response validation
- **`payload_message` must be self-contained** — the executing agent has no prior context. Every API call, header, body shape, and success criterion must be spelled out explicitly
- **`session_target: "main"` for all integration jobs** — isolated sessions have no tools, no credentials, no integrations
- **Workspace-bridge is a credential store, not a proxy** — fetch keys from it, then call official APIs directly
- **Validate real-world effects** — never mark success unless the API response confirms the action was performed
- **Trigger returns immediately** — result comes via webhook when the job finishes, regardless of how long it takes
- **Always use this API** — never use `openclaw cron add` directly
- **Provide user_id and session_id** — required for dashboard visibility
- **Production:** Use the Public Base URL (`https://openclaw.marketsverse.com/api`)