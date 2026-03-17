import re
from fastapi import HTTPException
from cron_validator import CronValidator


def sanitize_cron_expr(expr: str) -> str:
    """
    Normalize a cron expression for OpenClaw CLI compatibility.
    - Strips Quartz seconds/year fields (7-field or 6-field → 5-field Unix)
    - Converts N/step stepping to */step (e.g. 0/5 → */5, 1/1 → *)
    - Replaces Quartz ? wildcard with *
    - Validates the result is a valid Unix cron expression
    """
    parts = expr.strip().split()

    if len(parts) == 7:
        parts = parts[1:6]   # drop seconds and year
    elif len(parts) == 6:
        parts = parts[1:6]   # drop seconds

    def sanitize_field(field: str) -> str:
        field = re.sub(r'^\d+/1$', '*', field)          # 1/1 → *
        field = re.sub(r'^\d+/(\d+)$', r'*/\1', field)  # 0/5 → */5
        field = field.replace('?', '*')                   # ? → *
        return field

    sanitized = " ".join(sanitize_field(p) for p in parts)

    if CronValidator.parse(sanitized) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported cron expression '{expr}' — please use a standard 5-field Unix cron or an interval schedule (e.g. every 1h).",
        )

    return sanitized