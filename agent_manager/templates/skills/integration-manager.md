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

### 2. Make an API Request via Proxy
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

## Example Usage

When instructed to interact with an external service like Slack:
1. Call `GET /api/integrations/agent/my-agent-id` to see if a Slack integration is available.
2. If available, extract its `integration_id`, `base_url`, and deeply read its `usage_instructions`.
3. Construct your HTTP requests to the third-party API strictly through the proxy `POST /api/integrations/{integration_id}/proxy`, passing the target endpoint in the `path` field, and the payload in the `body` field.
4. The backend will return the exact JSON response from the third-party service.
