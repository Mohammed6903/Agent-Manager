# Cron Templates & Global Integrations

Reference guide for creating, managing, and using **Cron Templates** and **Global Integrations** in the OpenClaw API.

---

## Table of Contents

1. [Integrations](#integrations)
   - [Concept](#concept)
   - [Assign an Integration to an Agent](#assign-an-integration-to-an-agent)
   - [Auth Schemes](#auth-schemes)
   - [Manage Integrations](#manage-integrations)
2. [Cron Templates](#cron-templates)
   - [Concept](#concept-1)
   - [Variables](#variables)
   - [Schedule Kinds](#schedule-kinds)
   - [Pipeline Templates](#pipeline-templates)
   - [Create a Cron Template](#create-a-cron-template)
   - [Instantiate a Template into a Live Cron Job](#instantiate-a-template-into-a-live-cron-job)
   - [Manage Templates](#manage-templates)
3. [End-to-End Example](#end-to-end-example)

---

## Integrations

### Concept

An **Integration** is a registry entry that describes a third-party API — its base URL, authentication shape, and available endpoints. They are hardcoded in the backend.

When an agent needs to use an external API, it is provided an `IntegrationClient` instance that automatically injects the stored credentials. 

---

### Assign an Integration to an Agent

Once an integration is available in the hardcoded registry, you assign it to a specific agent along with that agent's credentials.

`POST /api/integrations/assign`

```json
{
  "agent_id": "my-agent-id",
  "integration_name": "slack",
  "credentials": {
    "bot_token": "xoxb-..."
  }
}
```

- `credentials` keys must match the `name` values declared in `auth_fields`.
- All `required: true` fields must be present; optional fields can be omitted.
- Credentials are encrypted and stored; they are never returned in plain text after this call.

---

### Auth Schemes

The `auth_scheme` object tells the proxy how to inject credentials:

#### Bearer / token header

```json
{
  "type": "bearer",
  "header": "Authorization",
  "prefix": "Bearer"        // or "token", "Bot", etc.
}
```

The proxy builds: `Authorization: Bearer <credential_value>`

#### API Key in header

```json
{
  "type": "api_key",
  "header": "X-Api-Key"
}
```

The proxy builds: `X-Api-Key: <credential_value>`

#### Basic Auth

```json
{
  "type": "basic",
  "username_field": "username",
  "password_field": "password"
}
```

The proxy base64-encodes `username:password` into the `Authorization` header.

#### OAuth 1.0a (Twitter / X)

Used for APIs that require per-request HMAC-SHA1 signing with four credentials:

```json
{
  "type": "oauth1",
  "consumer_key_field": "api_key",
  "consumer_secret_field": "api_secret",
  "token_field": "access_token",
  "token_secret_field": "access_secret"
}
```

The four `*_field` values must match the `name` keys in your `auth_fields` array. The proxy:

1. Reads all four credentials from the encrypted secret store
2. Generates a unique nonce and timestamp per request
3. Builds the OAuth signature base string from the HTTP method, full URL, and params
4. Computes the HMAC-SHA1 signature using the consumer secret + token secret as the signing key
5. Assembles the `Authorization: OAuth ...` header with all OAuth parameters

The agent never handles signing — it sends a normal proxy request and the header is injected automatically.

#### Summary of Auth Scheme Types

| `type` | Credential fields needed | Header produced |
|---|---|---|
| `bearer` | `token_field` | `Authorization: Bearer <token>` |
| `api_key_header` | `token_field` | `<header_name>: <token>` |
| `api_key_query` | `token_field` | *(added as query param)* |
| `basic` | `username_field`, `password_field` | `Authorization: Basic <base64>` |
| `oauth1` | `consumer_key_field`, `consumer_secret_field`, `token_field`, `token_secret_field` | `Authorization: OAuth oauth_consumer_key=..., oauth_signature=..., ...` |

Additionally, any scheme can include `"extra_headers"` for injecting arbitrary headers with `{credential_field}` interpolation:

```json
{
  "type": "bearer",
  "token_field": "bot_token",
  "extra_headers": {
    "X-Custom-Org": "{org_id}"
  }
}
```

---



### Manage Integrations

| Action | Method | Path |
|---|---|---|
| List all | `GET` | `/api/integrations` |
| Get one | `GET` | `/api/integrations/{name}` |
| Assign agent integration | `POST` | `/api/integrations/assign` |
| Get agent's integrations | `GET` | `/api/integrations/agent/{agent_id}` |
| Get decrypted credentials | `GET` | `/api/integrations/{name}/credentials?agent_id=...` |
| View request logs | `GET` | `/api/integrations/{name}/logs` |

---

---

## Cron Templates

### Concept

A **Cron Template** is a reusable blueprint for creating scheduled agent jobs. Instead of writing out a full cron job payload from scratch every time, you define:

- A **schedule** (fixed or parameterised).
- A **payload message** (the prompt the agent receives) with `{variable}` placeholders.
- An optional structured **pipeline template**.
- Which **global integrations** the agent must have assigned before the job can run.
- A list of **variables** that the caller fills in at instantiation time.

When a user calls **instantiate**, the API:
1. Validates all required variables are provided.
2. Verifies the agent has the required integrations assigned.
3. Substitutes `{variable}` placeholders in the message and pipeline.
4. Injects proxy instructions for every required integration.
5. Creates a live cron job in OpenClaw automatically.

---

### Variables

Variables let you parameterise the template prompt and pipeline. They are declared in the `variables` array:

```json
{
  "key": "notion_page_id",    // placeholder name used in {notion_page_id}
  "label": "Notion Page ID",  // shown to the user filling the form
  "required": true,
  "default": null             // optional fallback value
}
```

In `payload_message` (and `pipeline_template`) reference them as `{key}`:

```
Summarise the Notion page with ID {notion_page_id} and post the summary to Slack channel {slack_channel}.
```

At instantiation time the caller provides:

```json
{
  "variable_values": {
    "notion_page_id": "abc123",
    "slack_channel": "C0987654"
  }
}
```

---

### Schedule Kinds

| `schedule_kind` | `schedule_expr` format | Example |
|---|---|---|
| `"every"` | duration string | `"30m"`, `"2h"`, `"1d"` |
| `"cron"` | standard 5-field cron | `"0 9 * * 1-5"` |
| `"at"` | ISO 8601 timestamp | `"2026-06-01T09:00:00Z"` |

For `schedule_kind: "cron"` you may also set:
- `schedule_tz` — IANA timezone (e.g. `"America/New_York"`). Defaults to UTC.
- `schedule_human` — optional English description shown in the UI (e.g. `"Every weekday at 9 AM"`).

---

### Pipeline Templates

`pipeline_template` is an optional JSON object/array that defines a structured multi-step execution plan. When present, it is appended to the payload message under a `## PIPELINE EXECUTION FRAMEWORK` header so the agent follows the exact steps you specify.

Variables are substituted recursively throughout the entire pipeline structure. Example:

```json
{
  "pipeline_template": [
    {
      "step": 1,
      "action": "fetch_data",
      "source": "Notion page {notion_page_id}",
      "output_var": "page_content"
    },
    {
      "step": 2,
      "action": "summarise",
      "input_var": "page_content",
      "output_var": "summary"
    },
    {
      "step": 3,
      "action": "post_to_slack",
      "channel": "{slack_channel}",
      "message": "{{summary}}"
    }
  ]
}
```

---

### Create a Cron Template

`POST /api/cron-templates?user_id=<user_id>`

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✓ | Display name of the template |
| `description` | string | | Short description shown in the UI |
| `category` | string | | Grouping label (e.g. `"reporting"`, `"notifications"`) |
| `is_public` | boolean | | `false` = private (default). `true` = visible to all users |
| `required_integrations` | array of UUIDs | | IDs of global integrations the agent must have assigned |
| `variables` | array | | Variable declarations (see [Variables](#variables)) |
| `schedule_kind` | string | ✓ | `"every"`, `"cron"`, or `"at"` |
| `schedule_expr` | string | ✓ | Schedule expression matching `schedule_kind` |
| `schedule_tz` | string | | IANA timezone. Only used when `schedule_kind` is `"cron"` |
| `schedule_human` | string | | Human-readable schedule label |
| `session_target` | string | | `"isolated"` (default) or `"main"` |
| `delivery_mode` | string | | `"webhook"` (default) or `"none"` |
| `payload_message` | string | ✓ | Agent prompt; use `{variable_key}` for substitution |
| `pipeline_template` | object/array | | Structured pipeline definition (optional) |

---

#### Example — Daily Slack Digest (no integrations)

```json
POST /api/cron-templates?user_id=user_001
{
  "name": "Daily Slack Digest",
  "description": "Posts a morning summary of pending tasks to a Slack channel.",
  "category": "notifications",
  "is_public": false,
  "variables": [
    { "key": "slack_channel", "label": "Slack Channel ID", "required": true },
    { "key": "timezone",      "label": "Timezone",         "required": false, "default": "UTC" }
  ],
  "schedule_kind": "cron",
  "schedule_expr": "0 9 * * 1-5",
  "schedule_tz": "UTC",
  "schedule_human": "Every weekday at 9 AM",
  "session_target": "isolated",
  "delivery_mode": "webhook",
  "payload_message": "Good morning! Summarise all open tasks and post a concise digest to Slack channel {slack_channel}. Consider the user's timezone as {timezone}."
}
```

---

#### Example — Notion → Slack Weekly Report (with integrations)

First make sure the Notion and Slack global integrations exist and note their UUIDs.

```json
POST /api/cron-templates?user_id=user_001
{
  "name": "Weekly Notion → Slack Report",
  "description": "Fetches a Notion page and posts a weekly summary to Slack.",
  "category": "reporting",
  "is_public": true,
  "required_integrations": [
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222222"
  ],
  "variables": [
    { "key": "notion_page_id", "label": "Notion Page ID",   "required": true },
    { "key": "slack_channel",  "label": "Slack Channel ID", "required": true }
  ],
  "schedule_kind": "cron",
  "schedule_expr": "0 8 * * 1",
  "schedule_tz": "Europe/London",
  "schedule_human": "Every Monday at 8 AM London time",
  "payload_message": "Fetch the Notion page {notion_page_id}, write a 3-bullet weekly summary, then post it to Slack channel {slack_channel}.",
  "pipeline_template": [
    { "step": 1, "action": "fetch_notion_page",  "page_id": "{notion_page_id}" },
    { "step": 2, "action": "generate_summary",   "max_bullets": 3 },
    { "step": 3, "action": "post_slack_message", "channel": "{slack_channel}" }
  ]
}
```

---

#### Example — One-time scheduled task

```json
POST /api/cron-templates?user_id=user_001
{
  "name": "One-time Report",
  "description": "Runs once at a specific time.",
  "variables": [
    { "key": "report_date", "label": "Report Date (YYYY-MM-DD)", "required": true }
  ],
  "schedule_kind": "at",
  "schedule_expr": "2026-06-01T09:00:00Z",
  "payload_message": "Generate the end-of-quarter report for {report_date} and email it."
}
```

---

### Instantiate a Template into a Live Cron Job

`POST /api/cron-templates/{template_id}/instantiate`

This creates a real, running cron job in OpenClaw from the template.

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `agent_id` | string | ✓ | The agent that will run the job |
| `user_id` | string | ✓ | The user performing the instantiation |
| `session_id` | string | ✓ | Session to associate ownership with |
| `variable_values` | object | | Key-value pairs for every declared variable |

```json
POST /api/cron-templates/abc-template-id/instantiate
{
  "agent_id":        "agent-xyz",
  "user_id":         "user_001",
  "session_id":      "sess_abc123",
  "variable_values": {
    "notion_page_id": "abc123def456",
    "slack_channel":  "C0987654"
  }
}
```

**What happens:**
1. All `required: true` variables without a `default` must be in `variable_values` — otherwise `400`.
2. The agent must have every integration listed in `required_integrations` already assigned — otherwise `400` with the missing integration name.
3. Variables are substituted into `payload_message` and `pipeline_template`.
4. The system prepends a proxy-usage guide for each required integration so the agent knows exactly how to call them.
5. A live cron job is created and returns its `job_id`.

---

### Manage Templates

| Action | Method | Path |
|---|---|---|
| Create | `POST` | `/api/cron-templates?user_id=...` |
| List (own + public) | `GET` | `/api/cron-templates?user_id=...` |
| Get one | `GET` | `/api/cron-templates/{id}?user_id=...` |
| Update (owner only) | `PATCH` | `/api/cron-templates/{id}?user_id=...` |
| Delete (owner only) | `DELETE` | `/api/cron-templates/{id}?user_id=...` |
| Instantiate | `POST` | `/api/cron-templates/{id}/instantiate` |

> Templates marked `is_public: true` are readable by all users but can only be updated or deleted by their creator.

---

---

## End-to-End Example

This example wires everything together: create an integration, assign it to an agent, build a template, and instantiate it.

### Step 1 — Register the Slack integration

```bash
curl -X POST http://localhost:8000/api/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Slack",
    "type": "slack",
    "api_type": "rest",
    "base_url": "https://slack.com/api",
    "auth_scheme": { "type": "bearer", "header": "Authorization", "prefix": "Bearer" },
    "auth_fields": [
      { "name": "bot_token", "label": "Bot Token", "required": true }
    ],
    "endpoints": [
      { "method": "POST", "path": "/chat.postMessage", "description": "Send a message" }
    ],
    "usage_instructions": "Call POST /chat.postMessage with { channel, text } to send messages."
  }'
# → { "id": "aaaaaaaa-...", ... }
```

### Step 2 — Assign it to the agent with credentials

```bash
curl -X POST http://localhost:8000/api/integrations/aaaaaaaa-.../assign \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-xyz",
    "credentials": { "bot_token": "xoxb-my-real-bot-token" }
  }'
```

### Step 3 — Create the cron template

```bash
curl -X POST "http://localhost:8000/api/cron-templates?user_id=user_001" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily Slack Standup",
    "category": "notifications",
    "required_integrations": ["aaaaaaaa-..."],
    "variables": [
      { "key": "channel", "label": "Channel ID", "required": true }
    ],
    "schedule_kind": "cron",
    "schedule_expr": "0 9 * * 1-5",
    "schedule_tz": "UTC",
    "schedule_human": "Weekdays at 9 AM",
    "payload_message": "Post a concise standup summary to Slack channel {channel}."
  }'
# → { "id": "tmpl-bbbb...", ... }
```

### Step 4 — Instantiate it

```bash
curl -X POST http://localhost:8000/api/cron-templates/tmpl-bbbb.../instantiate \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id":        "agent-xyz",
    "user_id":         "user_001",
    "session_id":      "sess_001",
    "variable_values": { "channel": "C0987654" }
  }'
# → { "job_id": "cron-cccc...", ... }
```

The agent will now run every weekday at 9 AM UTC, automatically proxying its Slack call through the stored credentials.
