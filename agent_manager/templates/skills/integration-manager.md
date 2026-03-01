---
description: Use external integrations like Slack, Notion, GitHub, and more. Retrieve credentials and instructions for assigned integrations.
---

# integration-manager Skill

You have the ability to use external integrations assigned to you by the user. 
An integration provides you with API credentials (like a bot token or an API key) to interact with external services.

By using this skill, you can discover which integrations are available to you, fetch their credentials, and read their specific usage instructions.

**IMPORTANT:** Always read the `usage_instructions` returned by the API for each integration. It will tell you exactly how to authenticate and which endpoints to use.

## API Endpoints

### 1. Register a New Global Integration
If the user asks you to add or manage a new integration, register it globally first. 
The `auth_scheme` tells the backend *how* to inject credentials. Tell him to assign it to you after registration.
```http
POST /api/integrations
```
**Request Body (`GlobalIntegrationCreate`):**
```json
{
  "name": "GitHub",
  "type": "github",
  "base_url": "https://api.github.com",
  "auth_scheme": {
    "type": "bearer",
    "token_field": "access_token",
    "extra_headers": {
      "X-GitHub-Api-Version": "{api_version}"
    }
  },
  "auth_fields": [
    {"name": "access_token", "label": "PAT", "required": true},
    {"name": "api_version", "label": "Version", "required": false}
  ],
  "endpoints": [
    {"method": "GET", "path": "/user", "description": "Get user details"}
  ],
  "usage_instructions": "Use Authorization: Bearer {access_token}"
}
```
*Supported `auth_scheme.type` values: `bearer`, `basic`, `api_key_header`, `api_key_query`.*

### 2. List Assigned Integrations
Find out what external integrations are assigned and available to you.
```http
GET /api/integrations/agent/{agent_id}
```
**Response:**
```json
{
  "integrations": [
    {
      "integration_id": "123e4567-e89b-12d3-a456-426614174000",
      "name": "Acme Slack",
      "type": "slack",
      "base_url": "https://slack.com/api",
      "auth_scheme": {
        "type": "bearer",
        "token_field": "bot_token"
      },
      "auth_fields": [
        {
          "name": "bot_token",
          "label": "Bot Token",
          "required": true
        }
      ],
      "usage_instructions": "To use Slack, include the bot token in the Authorization header as a Bearer token. Use POST /chat.postMessage to send messages."
    }
  ]
}
```

### 3. Make an API Request via Proxy
Agents should NEVER fetch raw credentials. Instead, you use the proxy endpoint to construct your request. The OpenClaw backend will automatically inject the required `Authorization` headers (like `bot_token` or `api_key`) and forward your request to the third-party service.

```http
POST /api/integrations/{integration_id}/proxy
```
**Request Body (`IntegrationProxyRequest`):**
```json
{
  "agent_id": "your-agent-id",
  "method": "POST",
  "path": "/chat.postMessage",
  "body": {
    "channel": "#general",
    "text": "Hello world!"
  },
  "headers": {},
  "params": {}
}
```
*Note: `path` is appended to the integration's `base_url`.*

**Response:** The exact JSON response from the third-party service. You MUST validate that the response contains the expected fields before marking a task as success.

### 4. Verify Integration Before Use (Heartbeat)
Use the main API heartbeat to verify connectivity before attempting integration calls.

```http
GET /api/heartbeat
```
**Response (on success):**
```json
{
  "status": "ok"
}
```
*Call this endpoint first to ensure the API is responding before making proxy calls to integrations.*

## Error Handling

When a proxy request fails, check the HTTP status code and handle accordingly:

| Status | Meaning | Action |
|--------|---------|--------|
| `4xx` (except 429) | Invalid request or auth issue | Fix the request body or check credentials |
| `401/403` | Unauthorized/Forbidden | Integration credentials may be invalid or expired |
| `429` | Rate limited | Retry after exponential backoff (2s, 4s, 8s) |
| `5xx` | Service error | Retry after delay (60s) |

**Always include the exact error response in task status** when marking a step as failed. Do not assume the error — report what the integration actually returned.

## Usage Workflows

### Standard Workflow — Before Using Any Integration
1. Verify API is live: `GET /api/heartbeat` (should return `{"status": "ok"}`)
2. List assigned integrations: `GET /api/integrations/agent/{agent_id}`
3. Find the integration you need and extract `integration_id`
4. Read `usage_instructions` carefully — they specify exact endpoint paths and required fields
5. Make a test proxy call via `POST /api/integrations/{integration_id}/proxy` with a safe read-only endpoint first
6. If the test call succeeds with expected fields, proceed with your actual operations

### Validation Pattern — After Each API Call
Always verify the response contains the expected fields:
- **Success**: Check for a unique identifier or status field (e.g., `id`, `message_ts`, `result`)
- **Failure**: If the field is absent or response is 4xx/5xx, mark the step as error with the full response body
- **Never assume** a request succeeded just because it sent — only count it if the response confirms the real-world action

### Batch Operations — Multiple Calls to Same Integration
If you need to make multiple calls to the same integration:
1. Test the integration once at the start
2. Reuse the same `integration_id` for all calls
3. If any call fails with 401/403, stop — credentials may have expired
4. If a call fails with 429, pause and retry after backoff

## Example Usage

When instructed to interact with an external service like Slack:
1. Verify the API is live: `GET /api/heartbeat` 
2. Call `GET /api/integrations/agent/my-agent-id` to see if a Slack integration is available.
3. If available, extract its `integration_id`, `base_url`, and deeply read its `usage_instructions`.
4. Make a test call via the proxy `POST /api/integrations/{integration_id}/proxy` using a safe read-only endpoint to verify credentials work.
5. Construct your actual HTTP requests strictly through the proxy, passing the target endpoint in the `path` field and the payload in the `body` field.
6. Validate the response contains the expected confirmation field before marking the step as success.
7. If the response is an error or missing expected fields, include the full response in the task error.
