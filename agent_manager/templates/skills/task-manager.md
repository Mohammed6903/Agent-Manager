---
name: task-manager
description: For multi-step, procedural, or execution-based requests, create a task board before beginning work. Update task status incrementally as steps are completed. Flag blockers or issues requiring human intervention. Keep updates concise and proportional to task complexity. Avoid using task tracking for simple informational responses.
trigger: "task|progress|update|status|working on|started|completed|issue|blocked|kanban|subtask|tracking"
tools: [shell]
metadata: {"openclaw": {"requires": {"bins": ["curl", "jq"]}}}
---

# Task Manager

Internal API: http://localhost:8000/api
Public Base: https://openclaw.marketsverse.com/api

## Your Identity
Your agent_id is your agent name in lowercase (e.g. aura, nexus, main).
Read it from your IDENTITY.md if unsure:
```bash
grep -i "agent id" ~/IDENTITY.md | awk -F: '{print $2}' | tr -d ' '

```

---

## WHEN TO USE

You MUST create a task **before** starting any non-trivial work. Update it as you make progress. This gives the human a live view of what you're doing.

**Workflow:**
1. **Starting work →** Create a task with status `assigned`, list planned sub-tasks
2. **Doing work →** Update status to `in_progress`, mark sub-tasks as done
3. **Hit a blocker →** Add an issue, set status to `error`
4. **Finished →** Set status to `completed`, ensure all sub-tasks are marked done
5. **Human resolves issue →** Check if issues are resolved, then retry

---

## CREATE A TASK

Call this when you begin any piece of work.

```bash
curl -s -X POST "http://localhost:8000/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "YOUR_ID",
    "title": "Short descriptive title",
    "description": "What you plan to do and why",
    "status": "assigned",
    "difficulty": "low|medium|high",
    "sub_tasks": [
      {"text": "Step 1 description", "done": false},
      {"text": "Step 2 description", "done": false}
    ],
    "context_pages": [
      {"context_name": "Relevant doc or page", "context_id": "unique-id"}
    ],
    "integrations": ["gmail", "calendar"],
    "issues": []
  }' | jq .

```

Save the returned `id` — you'll need it for updates.

---

## UPDATE A TASK

Use PATCH to update any field. Only send the fields you want to change.

### Mark progress (update sub-tasks and status)

```bash
curl -s -X PATCH "http://localhost:8000/api/tasks/TASK_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_progress",
    "sub_tasks": [
      {"text": "Step 1 description", "done": true},
      {"text": "Step 2 description", "done": false}
    ]
  }' | jq .

```

### Mark completed

```bash
curl -s -X PATCH "http://localhost:8000/api/tasks/TASK_ID" \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}' | jq .

```

### Report an issue (needs human help)

```bash
curl -s -X PATCH "http://localhost:8000/api/tasks/TASK_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "error",
    "issues": [
      {"description": "Clear description of what went wrong and what human action is needed", "resolved": false}
    ]
  }' | jq .

```

---

## CHECK IF ISSUE WAS RESOLVED

When you have a task in `error` status, periodically check if the human resolved your issue:

```bash
curl -s "http://localhost:8000/api/tasks/TASK_ID" | jq '.issues'

```

If an issue shows `"resolved": true`, the human has addressed it. Retry the work and update the task.

---

## LIST YOUR TASKS

```bash
# All your tasks
curl -s "http://localhost:8000/api/tasks?agent_id=YOUR_ID" | jq .

# Only in-progress tasks
curl -s "http://localhost:8000/api/tasks?agent_id=YOUR_ID&status=in_progress" | jq .

```

---

## GET A SINGLE TASK

```bash
curl -s "http://localhost:8000/api/tasks/TASK_ID" | jq .

```

---

## DELETE A TASK

```bash
curl -s -X DELETE "http://localhost:8000/api/tasks/TASK_ID" | jq .

```

---

## STATUS VALUES

| Status | Meaning |
|--------|---------|
| `assigned` | Task created, work not yet started |
| `in_progress` | Actively working on it |
| `completed` | All done |
| `error` | Blocked — check `issues` for details |

## DIFFICULTY VALUES

| Difficulty | Meaning |
|------------|---------|
| `low` | Quick, straightforward task |
| `medium` | Moderate effort, some complexity |
| `high` | Complex, time-consuming, or risky |

---

## Best Practices

* **Always create a task first** — even for simple work. The human wants visibility.
* **Update frequently** — mark sub-tasks done as you complete them, don't batch updates.
* **Be specific in issues** — describe exactly what you need from the human.
* **Use context_pages** — link relevant documents, threads, or IDs the human might need.
* **List integrations** — note which tools/services you're using (gmail, calendar, notion, etc.).
* **Production:** In remote environments, use the Public Base URL.
