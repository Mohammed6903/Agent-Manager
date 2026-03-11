"""S3 storage service for raw integration data."""
import json
import boto3
from botocore.exceptions import ClientError
from ..config import settings

def _client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )

# ── Key Helpers ──────────────────────────────────────────────────────────────

def gmail_raw_key(agent_id: str, message_id: str) -> str:
    return f"{agent_id}/gmail/raw/{message_id}.json"

def calendar_raw_key(agent_id: str, event_id: str) -> str:
    return f"{agent_id}/calendar/raw/{event_id}.json"

# ── Core Operations ──────────────────────────────────────────────────────────

def upload_json(key: str, data: dict) -> bool:
    """Upload a dict as JSON to S3. Returns True on success."""
    try:
        _client().put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return True
    except ClientError as e:
        print(f"S3 upload failed for {key}: {e}")
        return False

def download_json(key: str) -> dict | None:
    """Download and parse a JSON object from S3. Returns None if not found."""
    try:
        response = _client().get_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
        )
        return json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        print(f"S3 download failed for {key}: {e}")
        return None

def key_exists(key: str) -> bool:
    """Check if a key exists in S3 without downloading it."""
    try:
        _client().head_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return True
    except ClientError:
        return False

def list_keys(prefix: str) -> list[str]:
    """List all keys under a prefix. Handles pagination."""
    client = _client()
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.S3_BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys

def delete_key(key: str) -> bool:
    """Delete a single key from S3."""
    try:
        _client().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        print(f"S3 delete failed for {key}: {e}")
        return False

# ── Gmail Helpers ────────────────────────────────────────────────────────────

def save_gmail_raw(agent_id: str, message_id: str, raw: dict) -> bool:
    return upload_json(gmail_raw_key(agent_id, message_id), raw)

def load_gmail_raw(agent_id: str, message_id: str) -> dict | None:
    return download_json(gmail_raw_key(agent_id, message_id))

def gmail_message_exists(agent_id: str, message_id: str) -> bool:
    return key_exists(gmail_raw_key(agent_id, message_id))

def list_gmail_message_ids(agent_id: str) -> list[str]:
    """Return all message IDs already stored in S3 for this agent."""
    prefix = f"{agent_id}/gmail/raw/"
    keys = list_keys(prefix)
    # Extract message ID from key: "agent_id/gmail/raw/MSG_ID.json" → "MSG_ID"
    return [k.replace(prefix, "").replace(".json", "") for k in keys]


def delete_all_gmail_raw(agent_id: str) -> int:
    """Delete all stored Gmail messages for an agent from S3.

    Use before re-ingesting with the new parsed format so stale raw objects
    don't linger alongside clean ones.

    Returns:
        Number of objects deleted.
    """
    prefix = f"{agent_id}/gmail/raw/"
    keys = list_keys(prefix)
    for key in keys:
        delete_key(key)
    return len(keys)


def delete_gmail_namespace(agent_id: str) -> int:
    """Delete all Gmail S3 objects for an agent.

    This includes every object under ``{agent_id}/gmail/``.

    Returns:
        Number of deleted objects.
    """
    prefix = f"{agent_id}/gmail/"
    keys = list_keys(prefix)
    for key in keys:
        delete_key(key)
    return len(keys)

# ── Calendar Helpers ─────────────────────────────────────────────────────────

def save_calendar_raw(agent_id: str, event_id: str, raw: dict) -> bool:
    return upload_json(calendar_raw_key(agent_id, event_id), raw)

def load_calendar_raw(agent_id: str, event_id: str) -> dict | None:
    return download_json(calendar_raw_key(agent_id, event_id))