# Cron Templates & Global Integrations

Reference guide for creating, managing, and using **Cron Templates** and **Global Integrations** in the OpenClaw API.

---

## Table of Contents

1. [Global Integrations](#global-integrations)
   - [Concept](#concept)
   - [Create a Global Integration](#create-a-global-integration)
   - [Assign an Integration to an Agent](#assign-an-integration-to-an-agent)
   - [REST vs GraphQL Integrations](#rest-vs-graphql-integrations)
   - [Auth Schemes](#auth-schemes)
   - [Proxy Requests Through an Integration](#proxy-requests-through-an-integration)
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

## Global Integrations

### Concept

A **Global Integration** is a registry entry that describes a third-party API — its base URL, authentication shape, and available endpoints. It is defined once and can be assigned to many agents.

When an agent calls an external API it must do so **through the integration proxy**, which automatically injects the stored credentials. Agents never touch raw API keys.

```
Third-party API
      ↑
 Proxy endpoint  ←  agent curl call
      ↑
 GlobalIntegration  (URL, auth scheme, endpoints)
      ↑
 AgentIntegration   (agent_id + encrypted credentials)
```

---

### Create a Global Integration

`POST /api/integrations`

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✓ | Unique display name (e.g. `"Slack"`) |
| `type` | string | ✓ | Integration category (e.g. `"slack"`, `"notion"`, `"github"`) |
| `api_type` | string | | `"rest"` (default) or `"graphql"` |
| `status` | string | | `"active"` (default), `"inactive"`, or `"error"` |
| `base_url` | string | ✓ | Root URL of the API (e.g. `"https://slack.com/api"`) |
| `auth_scheme` | object | ✓ | Describes how auth headers are built (see [Auth Schemes](#auth-schemes)) |
| `auth_fields` | array | ✓ | Credential fields the user must supply when assigning (see below) |
| `endpoints` | array | ✓ | List of documented API endpoints |
| `request_transformers` | array | | Field-mapping rules applied before forwarding a request |
| `response_transformers` | array | | Field-mapping rules applied before returning a response |
| `usage_instructions` | string | ✓ | Human/agent-readable description of how to call this API |

#### `auth_fields` items

```json
{
  "name": "bot_token",       // key used in credential payloads
  "label": "Bot Token",      // human-readable label shown in UI
  "required": true
}
```

#### `endpoints` items

```json
{
  "method": "POST",
  "path": "/chat.postMessage",
  "description": "Send a message to a channel"
}
```

#### Example — Slack (REST, Bearer token)

```json
POST /api/integrations
{
  "name": "Slack",
  "type": "slack",
  "api_type": "rest",
  "base_url": "https://slack.com/api",
  "auth_scheme": {
    "type": "bearer",
    "header": "Authorization",
    "prefix": "Bearer"
  },
  "auth_fields": [
    { "name": "bot_token", "label": "Bot Token", "required": true }
  ],
  "endpoints": [
    { "method": "POST", "path": "/chat.postMessage",  "description": "Send a message" },
    { "method": "GET",  "path": "/conversations.list", "description": "List channels" }
  ],
  "usage_instructions": "Use POST /chat.postMessage with body {channel, text} to send messages. Use GET /conversations.list to enumerate channels."
}
```

#### Example — GitHub (REST, Personal Access Token)

```json
POST /api/integrations
{
  "name": "GitHub",
  "type": "github",
  "api_type": "rest",
  "base_url": "https://api.github.com",
  "auth_scheme": {
    "type": "bearer",
    "header": "Authorization",
    "prefix": "token"
  },
  "auth_fields": [
    { "name": "personal_access_token", "label": "Personal Access Token", "required": true }
  ],
  "endpoints": [
    { "method": "GET",  "path": "/user/repos",                   "description": "List repos" },
    { "method": "POST", "path": "/repos/{owner}/{repo}/issues",  "description": "Create issue" }
  ],
  "usage_instructions": "Prepend /repos/{owner}/{repo} for repo-scoped calls. Pass owner and repo as path segments."
}
```

#### Example — Linear (GraphQL)

```json
POST /api/integrations
{
  "name": "Linear",
  "type": "linear",
  "api_type": "graphql",
  "base_url": "https://api.linear.app/graphql",
  "auth_scheme": {
    "type": "api_key",
    "header": "Authorization"
  },
  "auth_fields": [
    { "name": "api_key", "label": "API Key", "required": true }
  ],
  "endpoints": [
    { "method": "POST", "path": "/graphql", "description": "GraphQL endpoint" }
  ],
  "usage_instructions": "Send GraphQL queries via POST /graphql with {query, variables}. Use the /proxy/graphql endpoint."
}
```

#### Example — Twitter / X (REST, OAuth 1.0a)

Twitter's API requires OAuth 1.0a signing, which uses four credentials to compute an HMAC-SHA1 signature per request. The proxy handles this automatically with the `oauth1` auth scheme.

```json
POST /api/integrations
{
  "name": "Twitter",
  "type": "twitter",
  "api_type": "rest",
  "base_url": "https://api.x.com/2",
  "auth_scheme": {
    "type": "oauth1",
    "consumer_key_field": "api_key",
    "consumer_secret_field": "api_secret",
    "token_field": "access_token",
    "token_secret_field": "access_secret"
  },
  "auth_fields": [
    { "name": "api_key",       "label": "API Key",              "required": true },
    { "name": "api_secret",    "label": "API Secret",           "required": true },
    { "name": "access_token",  "label": "Access Token",         "required": true },
    { "name": "access_secret", "label": "Access Token Secret",  "required": true }
  ],
  "endpoints": [
    { "method": "POST", "path": "/tweets",          "description": "Create a tweet" },
    { "method": "GET",  "path": "/users/me",        "description": "Get authenticated user" },
    { "method": "GET",  "path": "/tweets/search/recent", "description": "Search recent tweets" },
    { "method": "DELETE", "path": "/tweets/:id",    "description": "Delete a tweet" }
  ],
  "usage_instructions": "POST /tweets with body { \"text\": \"Hello!\" } to tweet. GET /users/me for the authenticated user. OAuth signature is computed automatically by the proxy."
}
```

Then assign it to an agent with all four credentials:

```json
POST /api/integrations/{twitter_integration_id}/assign
{
  "agent_id": "agent-xyz",
  "credentials": {
    "api_key":       "your-consumer-api-key",
    "api_secret":    "your-consumer-api-secret",
    "access_token":  "your-access-token",
    "access_secret": "your-access-token-secret"
  }
}
```

The agent calls the proxy like any other REST integration. The proxy computes the OAuth 1.0a signature automatically from the four stored credentials, the HTTP method, and the URL:

```bash
curl -X POST https://<host>/api/integrations/<twitter_id>/proxy \
  -H "Content-Type: application/json" \
  -d '{ "agent_id": "agent-xyz", "method": "POST", "path": "/tweets", "body": { "text": "Hello from my agent!" } }'
```

The agent **never** sees the API keys or computes signatures — the proxy does it all.

---

### Assign an Integration to an Agent

Once a global integration exists you assign it to a specific agent along with that agent's credentials.

`POST /api/integrations/{integration_id}/assign`

```json
{
  "agent_id": "my-agent-id",
  "credentials": {
    "bot_token": "xoxb-..."
  }
}
```

- `credentials` keys must match the `name` values declared in `auth_fields`.
- All `required: true` fields must be present; optional fields can be omitted.
- Credentials are encrypted and stored; they are never returned in plain text after this call.

---

### REST vs GraphQL Integrations

| | REST (`api_type: "rest"`) | GraphQL (`api_type: "graphql"`) |
|---|---|---|
| Proxy endpoint | `POST /api/integrations/{id}/proxy` | `POST /api/integrations/{id}/proxy/graphql` |
| Request shape | `{ agent_id, method, path, body, headers, params }` | `{ agent_id, query, variables }` |
| Auth injection | Header injected per `auth_scheme` | Header injected per `auth_scheme` |

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

### Request & Response Transformers

Transformers are optional field-mapping rules stored on the integration that automatically reshape payloads **before** the request is forwarded to the third-party API (`request_transformers`) and **after** the response is received (`response_transformers`). This decouples the agent from API-specific quirks — the agent always sends/receives a clean, consistent shape.

Both fields accept an **array of rule objects**. Rules are applied in order.

---

#### Rule Types

| `type` | What it does | Required fields |
|---|---|---|
| `map` | Move (and optionally transform) a value from `source` path to `target` path, deleting the original | `source`, `target` |
| `add` | Add a field at `target` with a hard-coded `value` if the field doesn't already exist | `target`, `value` |
| `extract` | Copy a nested value up to `target` (does **not** delete the source) | `source`, `target` |
| `rename` | Rename a **top-level** key from `old_name` to `new_name` | `old_name`, `new_name` |
| `delete` | Remove the field at `target` path | `target` |

For `map` you can optionally add `"transform": "stringify"` or `"transform": "parse_json"` to coerce types during the move.

Paths use **dot notation** for nested fields: `"author.id"` → `{ "author": { "id": ... } }`.

---

#### Example — LinkedIn UGC Posts (request + response)

LinkedIn's `ugcPosts` API uses a deeply nested body format that differs from how an agent would naturally express a post. Transformers normalise both sides.

**Scenario:** The agent sends a flat body `{ "text": "Hello!", "visibility": "PUBLIC" }` but LinkedIn requires a nested structure. The API response also returns a deeply nested object that should be flattened for the agent.

```json
POST /api/integrations
{
  "name": "LinkedIn",
  "type": "linkedin",
  "api_type": "rest",
  "base_url": "https://api.linkedin.com/v2",
  "auth_scheme": { "type": "bearer", "header": "Authorization", "prefix": "Bearer" },
  "auth_fields": [
    { "name": "access_token", "label": "Access Token", "required": true },
    { "name": "person_urn",   "label": "Person URN (urn:li:person:...)", "required": true }
  ],
  "endpoints": [
    { "method": "POST", "path": "/ugcPosts", "description": "Create a post" }
  ],
  "request_transformers": [
    {
      "comment": "Wrap the agent's plain text into LinkedIn's specificContent structure",
      "type": "map",
      "source": "text",
      "target": "specificContent.com.linkedin.ugc.ShareContent.shareCommentary.text"
    },
    {
      "comment": "Move visibility string into LinkedIn's deeply nested visibility object",
      "type": "map",
      "source": "visibility",
      "target": "visibility.com.linkedin.ugc.MemberNetworkVisibility"
    },
    {
      "comment": "LinkedIn requires a mediaCategory field even for text-only posts",
      "type": "add",
      "target": "specificContent.com.linkedin.ugc.ShareContent.shareMediaCategory",
      "value": "NONE"
    },
    {
      "comment": "LinkedIn requires a lifecycleState field",
      "type": "add",
      "target": "lifecycleState",
      "value": "PUBLISHED"
    },
    {
      "comment": "LinkedIn requires a distribution block",
      "type": "add",
      "target": "distribution",
      "value": {
        "feedDistribution": "MAIN_FEED",
        "targetEntities": [],
        "thirdPartyDistributionChannels": []
      }
    }
  ],
  "response_transformers": [
    {
      "comment": "Extract the new post's ID from the deeply nested response to the top level",
      "type": "extract",
      "source": "value.id",
      "target": "post_id"
    },
    {
      "comment": "Remove the raw nested value block agents don't need",
      "type": "delete",
      "target": "value"
    }
  ],
  "usage_instructions": "POST to /ugcPosts with { text, visibility }. visibility must be PUBLIC or CONNECTIONS."
}
```

**Agent sends:**
```json
{ "text": "Hello LinkedIn!", "visibility": "PUBLIC" }
```

**What LinkedIn actually receives (after request transformers):**
```json
{
  "lifecycleState": "PUBLISHED",
  "distribution": {
    "feedDistribution": "MAIN_FEED",
    "targetEntities": [],
    "thirdPartyDistributionChannels": []
  },
  "specificContent": {
    "com.linkedin.ugc.ShareContent": {
      "shareMediaCategory": "NONE",
      "shareCommentary": { "text": "Hello LinkedIn!" }
    }
  },
  "visibility": {
    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
  }
}
```

**LinkedIn's raw response:**
```json
{ "value": { "id": "urn:li:ugcPost:7654321" } }
```

**What the agent receives (after response transformers):**
```json
{ "post_id": "urn:li:ugcPost:7654321" }
```

---

#### Example — Renaming fields (Notion)

Some APIs return fields with names that differ from what your agent expects. Use `rename` to standardise them without a nested path.

```json
"response_transformers": [
  {
    "comment": "Notion returns 'object' but agents expect 'type'",
    "type": "rename",
    "old_name": "object",
    "new_name": "type"
  },
  {
    "comment": "Flatten the page title out of Notion's nested title array",
    "type": "extract",
    "source": "properties.Name.title.0.plain_text",
    "target": "title"
  }
]
```

---

#### Example — Type coercion with `map`

Use the optional `transform` field to coerce a value's type while moving it:

```json
"request_transformers": [
  {
    "comment": "API expects the numeric ID as a string",
    "type": "map",
    "source": "issue_id",
    "target": "issueId",
    "transform": "stringify"
  }
]
```

Supported `transform` values:

| Value | Effect |
|---|---|
| `"stringify"` | Converts the value to a string via `str()` |
| `"parse_json"` | Parses a JSON string into a dict/array |
| `null` / omit | No coercion — value is moved as-is |

---

### Proxy Requests Through an Integration

Agents call external APIs through the proxy so credentials are never exposed:

#### REST

```bash
curl -X POST https://<host>/api/integrations/<integration_id>/proxy \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent-id",
    "method": "POST",
    "path": "/chat.postMessage",
    "body": { "channel": "C1234567", "text": "Hello from the agent!" }
  }'
```

#### GraphQL

```bash
curl -X POST https://<host>/api/integrations/<integration_id>/proxy/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent-id",
    "query": "query { viewer { login } }",
    "variables": {}
  }'
```

---

### Manage Integrations

| Action | Method | Path |
|---|---|---|
| List all | `GET` | `/api/integrations` |
| Get one | `GET` | `/api/integrations/{id}` |
| Update | `PATCH` | `/api/integrations/{id}` |
| Delete | `DELETE` | `/api/integrations/{id}` |
| Get agent's integrations | `GET` | `/api/integrations/agent/{agent_id}` |
| Get decrypted credentials | `GET` | `/api/integrations/{id}/credentials?agent_id=...` |
| View request logs | `GET` | `/api/integrations/{id}/logs` |

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
