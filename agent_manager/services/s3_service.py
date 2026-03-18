"""S3 storage service for raw integration data."""
from __future__ import annotations

import json
from collections.abc import Callable

import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.exceptions import ClientError
from ..config import settings

def _client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )

# ── Generic Key / CRUD ──────────────────────────────────────────────────────

def raw_key(agent_id: str, integration: str, item_id: str) -> str:
    """Build the S3 key for any integration's raw item."""
    return f"{agent_id}/{integration}/raw/{item_id}.json"


def save_raw(agent_id: str, integration: str, item_id: str, data: dict) -> bool:
    """Save a raw item dict to S3 under the integration namespace."""
    return upload_json(raw_key(agent_id, integration, item_id), data)


def load_raw(agent_id: str, integration: str, item_id: str) -> dict | None:
    """Load a raw item from S3. Returns None if not found."""
    return download_json(raw_key(agent_id, integration, item_id))


def list_item_ids(agent_id: str, integration: str) -> list[str]:
    """Return all item IDs stored in S3 for agent + integration."""
    prefix = f"{agent_id}/{integration}/raw/"
    keys = list_keys(prefix)
    return [k.replace(prefix, "").replace(".json", "") for k in keys]


def delete_namespace(agent_id: str, integration: str) -> int:
    """Delete all S3 objects for agent + integration. Returns count."""
    prefix = f"{agent_id}/{integration}/"
    keys = list_keys(prefix)
    for key in keys:
        delete_key(key)
    return len(keys)


# ── Backwards-compat aliases ────────────────────────────────────────────────
# Kept so existing callers (ingest_task, pipeline_service, etc.) don't break.

def gmail_raw_key(agent_id: str, message_id: str) -> str:
    return raw_key(agent_id, "gmail", message_id)

def calendar_raw_key(agent_id: str, event_id: str) -> str:
    return raw_key(agent_id, "calendar", event_id)

def save_gmail_raw(agent_id: str, message_id: str, raw_data: dict) -> bool:
    return save_raw(agent_id, "gmail", message_id, raw_data)

def load_gmail_raw(agent_id: str, message_id: str) -> dict | None:
    """Load a stored email from S3, returning None if it is expired."""
    key = gmail_raw_key(agent_id, message_id)
    if _is_expired(key):
        return None
    return download_json(key)

def save_calendar_raw(agent_id: str, event_id: str, raw_data: dict) -> bool:
    return save_raw(agent_id, "calendar", event_id, raw_data)

def load_calendar_raw(agent_id: str, event_id: str) -> dict | None:
    return load_raw(agent_id, "calendar", event_id)

def list_gmail_message_ids(agent_id: str) -> list[str]:
    """Return message IDs in S3 for this agent, excluding expired objects."""
    prefix = f"{agent_id}/gmail/raw/"
    keys = list_keys(prefix)
    if not keys:
        return []

    def _keep(key: str) -> tuple[str, bool]:
        return (key, not _is_expired(key))

    active_keys: list[str] = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for key, keep in executor.map(_keep, keys):
            if keep:
                active_keys.append(key)

    return [k.replace(prefix, "").replace(".json", "") for k in active_keys]

def list_calendar_event_ids(agent_id: str) -> list[str]:
    return list_item_ids(agent_id, "calendar")

def delete_gmail_namespace(agent_id: str) -> int:
    return delete_namespace(agent_id, "gmail")

def delete_calendar_namespace(agent_id: str) -> int:
    return delete_namespace(agent_id, "calendar")

def gmail_message_exists(agent_id: str, message_id: str) -> bool:
    key = gmail_raw_key(agent_id, message_id)
    if not key_exists(key):
        return False
    return not _is_expired(key)

def delete_all_gmail_raw(agent_id: str) -> int:
    prefix = f"{agent_id}/gmail/raw/"
    keys = list_keys(prefix)
    for key in keys:
        delete_key(key)
    return len(keys)

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

# ── Gmail Soft-Delete (Gmail-specific) ───────────────────────────────────────

_EXPIRED_TAG_KEY = "status"
_EXPIRED_TAG_VALUE = "expired"


def _is_expired(key: str) -> bool:
    """Return True if the S3 object carries the status=expired tag."""
    try:
        resp = _client().get_object_tagging(
            Bucket=settings.S3_BUCKET_NAME, Key=key
        )
        return any(
            t["Key"] == _EXPIRED_TAG_KEY and t["Value"] == _EXPIRED_TAG_VALUE
            for t in resp.get("TagSet", [])
        )
    except ClientError:
        return False


def list_all_gmail_message_ids_with_status(agent_id: str) -> dict[str, bool]:
    """Return all message IDs mapped to expired status (True=expired)."""
    prefix = f"{agent_id}/gmail/raw/"
    keys = list_keys(prefix)
    if not keys:
        return {}

    def _check_status(key: str) -> tuple[str, bool]:
        return (key, _is_expired(key))

    results: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        for key, is_expired in executor.map(_check_status, keys):
            msg_id = key.replace(prefix, "").replace(".json", "")
            results[msg_id] = is_expired

    return results


def tag_gmail_as_expired(
    agent_id: str, progress_callback: Callable[[int, int], None] | None = None
) -> int:
    """Tag all Gmail raw objects as expired for soft-delete."""
    prefix = f"{agent_id}/gmail/raw/"
    keys = list_keys(prefix)

    if not keys:
        if progress_callback:
            progress_callback(0, 0)
        return 0

    client = _client()
    total = len(keys)

    def _tag_key(key: str) -> bool:
        try:
            client.put_object_tagging(
                Bucket=settings.S3_BUCKET_NAME,
                Key=key,
                Tagging={"TagSet": [{"Key": _EXPIRED_TAG_KEY, "Value": _EXPIRED_TAG_VALUE}]},
            )
            return True
        except ClientError as e:
            print(f"Failed to tag {key}: {e}")
            return False

    tagged = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(_tag_key, k): k for k in keys}
        for i, future in enumerate(as_completed(futures), 1):
            if future.result():
                tagged += 1
            if progress_callback and (i % 50 == 0 or i == total):
                progress_callback(i, total)

    _ensure_lifecycle_rule()

    return tagged


def untag_gmail_as_expired(agent_id: str, message_ids: list[str]) -> int:
    """Restore soft-deleted Gmail raw objects by removing their tags."""
    if not message_ids:
        return 0

    client = _client()

    def _untag_key(msg_id: str) -> bool:
        key = gmail_raw_key(agent_id, msg_id)
        try:
            client.delete_object_tagging(
                Bucket=settings.S3_BUCKET_NAME,
                Key=key,
            )
            return True
        except ClientError as e:
            print(f"Failed to untag {key}: {e}")
            return False

    untagged = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        for result in executor.map(_untag_key, message_ids):
            if result:
                untagged += 1

    return untagged


def _ensure_lifecycle_rule() -> None:
    """Set up S3 lifecycle rule to auto-delete status=expired objects after 30 days."""
    client = _client()
    try:
        lifecycle_config = {
            "Rules": [
                {
                    "ID": "DeleteExpiredData",
                    "Filter": {
                        "Tag": {
                            "Key": _EXPIRED_TAG_KEY,
                            "Value": _EXPIRED_TAG_VALUE,
                        }
                    },
                    "Status": "Enabled",
                    "Expiration": {"Days": 30},
                }
            ]
        }
        client.put_bucket_lifecycle_configuration(
            Bucket=settings.S3_BUCKET_NAME,
            LifecycleConfiguration=lifecycle_config,
        )
        print(f"[S3] Lifecycle rule set: delete objects tagged status=expired after 30 days")
    except Exception as e:
        print(f"[S3] Failed to set lifecycle rule: {e}")
