"""Async wrappers around the `openclaw` CLI and shell commands."""
from __future__ import annotations
import asyncio
import json
import logging
import os
from typing import Any
from fastapi import HTTPException

logger = logging.getLogger("agent_manager.openclaw")

# AWS env vars that openclaw auto-detects and tries to use for Bedrock discovery.
# We strip these so openclaw doesn't attempt Bedrock when we only need S3.
_AWS_VARS_TO_STRIP = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "AWS_PROFILE",
}

def _openclaw_env() -> dict[str, str]:
    """Return os.environ without AWS credentials so openclaw doesn't auto-detect Bedrock."""
    return {k: v for k, v in os.environ.items() if k not in _AWS_VARS_TO_STRIP}


async def run_openclaw(args: list[str]) -> dict[str, Any]:
    """Run an ``openclaw`` CLI command and return parsed JSON output.
    Raises :class:`HTTPException` (500) when the command exits non-zero.
    """
    proc = await asyncio.create_subprocess_exec(
        "openclaw",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_openclaw_env(),
    )
    stdout, stderr = await proc.communicate()
    stdout_text = stdout.decode().strip()
    stderr_text = stderr.decode().strip()

    if proc.returncode != 0:
        logger.error("openclaw %s failed (rc=%s): %s", args, proc.returncode, stderr_text)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "openclaw_cli_error",
                "command": f"openclaw {' '.join(args)}",
                "exit_code": proc.returncode,
                "stderr": stderr_text or "(no stderr output)",
                "stdout": stdout_text or "(no stdout output)",
            },
        )

    if not stdout_text:
        return {}

    try:
        return json.loads(stdout_text)
    except json.JSONDecodeError:
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = stdout_text.find(start_char)
            end = stdout_text.rfind(end_char)
            if start != -1 and end > start:
                try:
                    return json.loads(stdout_text[start:end + 1])
                except json.JSONDecodeError:
                    continue
        return {"raw": stdout_text}


async def run_openclaw_raw(args: list[str]) -> str:
    """Run an ``openclaw`` CLI command and return raw stdout as a string."""
    proc = await asyncio.create_subprocess_exec(
        "openclaw",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_openclaw_env(),
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        stderr_text = stderr.decode().strip()
        logger.error("openclaw %s failed (rc=%s): %s", args, proc.returncode, stderr_text)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "openclaw_cli_error",
                "command": f"openclaw {' '.join(args)}",
                "exit_code": proc.returncode,
                "stderr": stderr_text or "(no stderr output)",
            },
        )

    return stdout.decode().strip()


async def run_shell(cmd: str) -> str:
    """Run an arbitrary shell command and return stdout.
    Raises :class:`HTTPException` (500) on non-zero exit.
    """
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        stderr_text = stderr.decode().strip()
        logger.error("shell cmd failed (%s): %s", cmd, stderr_text)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "shell_command_error",
                "command": cmd,
                "exit_code": proc.returncode,
                "stderr": stderr_text or "(no stderr output)",
            },
        )

    return stdout.decode().strip()