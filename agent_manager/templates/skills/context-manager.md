---
description: Read global knowledge topics and contexts assigned to you
---

# context-manager Skill

You have the ability to read knowledge contexts assigned to you by the user.

A context is a document containing background knowledge or specific instructions related to a topic. By using this skill, you can fetch those contexts to learn how to properly execute a task or understand its constraints.

The user mandate is that you **must** check your available contexts if you're not sure how to proceed with a request or if you need to adhere to specific guidelines.

## API Endpoints

### 1. List Available Contexts
Find out what context knowledge topics are assigned and available to you.
```http
GET /api/contexts/agent/{agent_id}
```
**Response:**
```json
{
  "contexts": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "name": "coding-guidelines",
      "content": "Always use 4 spaces...",
      "created_at": "2026-02-28T10:00:00Z"
    }
  ]
}
```

### 2. Fetch Context Content
Retrieve the full content of a specific context by its ID.
```http
GET /api/contexts/{context_id}/content?agent_id={agent_id}
```
**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "coding-guidelines",
  "content": "Always use 4 spaces for indentation. Never use tabs. Use snake_case for variables."
}
```

## Example Usage

When instructed to write some Python code, check if there are any contexts assigned to you first:
1. Call `GET /api/contexts/agent/my-agent-id` to get available contexts.
2. If you see one with name `"python-style-guide"`, grab its `id`.
3. Fetch it with `GET /api/contexts/{context_id}/content?agent_id=my-agent-id`.
4. Use the knowledge obtained to fulfill the user's request.
