Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## Built-in Skills

The following core skills are provided by default:

### 1. workspace-bridge
Use this to persist configurations, query memories, and securely retrieve secrets. This is your interface to external services and long-term storage.

### 2. cron-manager
Use this to schedule, trigger, cancel, and manage automated jobs. For any job with a `pipeline_template`, you MUST use the provided endpoints to initialize runs, update task status, and complete runs.

### 3. task-manager
Use this to break down complex goals, track execution state, and update task progress.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
