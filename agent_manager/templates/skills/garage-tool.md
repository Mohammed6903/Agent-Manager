---
name: garage-tool
description: Create posts on the Garage community feed. Use this whenever the user asks you to post, share, publish, or create something on the feed. This is the default tool for feed-related actions.
trigger: "feed|post|publish|share|garage|create post|write post|community|announcement"
---

# Garage Feed Tool

## WHEN TO USE

Use this skill **automatically** whenever the user asks you to:
- Create a post / feed entry
- Share something on the feed
- Publish an announcement
- Post to the Garage community

You do NOT need to be explicitly told to use this skill — if the user's intent matches any of the above, use it by default.

---

## HOW TO POST

Call the `create_garage_post` function with the content to publish:

```json
{
  "content": "The text content of the post",
  "channelIds": ["channel_id_here"]
}
```

- `content` is required — the text to publish
- `channelIds` is optional — use it if the user specifies a channel ID

---

## Error Handling

* **"not connected" / credentials missing:** Do NOT ask the user for a token or orgId in chat. Instead tell them:
  > "Please connect the Garage Feed skill first: go to **Agent Settings → Skills → Garage Feed → Connect**."

* **Post failed:** Report the error message back to the user clearly.

* **Content quality:** Write clear, well-formatted posts. Use proper grammar and punctuation.

* **Confirmations:** Always confirm with the user before posting, unless they've given explicit instructions to just post it.
