import uuid
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

print("--- Testing Multi-Credential Integration (GitHub-style) ---")

# ── 1. Create GlobalIntegration with multiple auth fields ──────────────────
print("\n1. Create GlobalIntegration (GitHub-style, 2 auth fields)")
integration_name = f"test-github-{uuid.uuid4().hex[:6]}"

res = client.post("/api/integrations", json={
    "name": integration_name,
    "type": "github",
    "base_url": "https://httpbin.org",  # httpbin mirrors back what we send
    "auth_fields": [
        {"name": "access_token", "label": "Personal Access Token", "required": True},
        {"name": "owner",        "label": "GitHub Username or Org", "required": True},
        {"name": "api_version",  "label": "API Version Header",     "required": False},
    ],
    "auth_scheme": {
        "type": "bearer",
        "token_field": "access_token",
        "extra_headers": {
            "X-Github-Api-Version": "{api_version}"
        }
    },
    "endpoints": [
        {"method": "GET",   "path": "/get",  "description": "List repos"},
        {"method": "POST",  "path": "/post", "description": "Create repo"},
    ],
    # usage_instructions tells the proxy HOW to inject credentials.
    # This is the critical field — it must describe the auth scheme so the
    # proxy knows whether to use Bearer, Basic, a custom header, query param, etc.
    "usage_instructions": (
        "Authenticate using Authorization: Bearer {access_token}. "
        "Also inject X-GitHub-Api-Version header using {api_version} if provided. "
        "The {owner} field is available for URL construction but not sent as a header."
    )
})
print("Status:", res.status_code)
assert res.status_code == 200, res.text
integration_id = res.json()["id"]
print("Integration ID:", integration_id)

# ── 2. Assign with multiple credentials ───────────────────────────────────
print("\n2. Assign Integration to Agent with multiple credentials")
agent_id = f"agent-{uuid.uuid4().hex[:6]}"

res = client.post(f"/api/integrations/{integration_id}/assign", json={
    "agent_id": agent_id,
    "credentials": {
        "access_token": "ghp_test_token_abc123",
        "owner":        "my-org",
        "api_version":  "2022-11-28",  # optional field — provided here
    }
})
print("Status:", res.status_code)
assert res.status_code == 200, res.text

# ── 3. Verify credentials were stored correctly ────────────────────────────
print("\n3. Verify stored credentials")
res = client.get(f"/api/integrations/{integration_id}/credentials?agent_id={agent_id}")
print("Status:", res.status_code)
assert res.status_code == 200, res.text
creds = res.json()["credentials"]
assert creds["access_token"] == "ghp_test_token_abc123"
assert creds["owner"]        == "my-org"
assert creds["api_version"]  == "2022-11-28"
print("Credentials verified:", creds)

# ── 4. Proxy GET — verify Bearer token and version header injected ─────────
print("\n4. Proxy GET — verify auth headers injected from credentials")
res = client.post(f"/api/integrations/{integration_id}/proxy", json={
    "agent_id": agent_id,
    "method":   "GET",
    "path":     "/get",
    "params":   {"per_page": "10"},
})
print("Status:", res.status_code)
assert res.status_code == 200, res.text
data = res.json()
print("Httpbin response headers:", data.get("headers", {}))
print("Httpbin response params:",  data.get("args", {}))

# Auth header injected from access_token
assert "Authorization" in data["headers"], "Missing Authorization header"
assert data["headers"]["Authorization"] == "Bearer ghp_test_token_abc123"

# Optional credential injected as custom header
assert "X-Github-Api-Version" in data["headers"], "Missing version header"
assert data["headers"]["X-Github-Api-Version"] == "2022-11-28"

# Query params passed through
assert data["args"].get("per_page") == "10"

# owner is NOT sent as a header — it's for URL construction only
assert "Owner" not in data["headers"], "owner should not be injected as a header"

print("\n5. Proxy POST — verify body + auth on write operation")
res = client.post(f"/api/integrations/{integration_id}/proxy", json={
    "agent_id": agent_id,
    "method":   "POST",
    "path":     "/post",
    "body":     {"name": "new-repo", "private": True},
})
print("Status:", res.status_code)
assert res.status_code == 200, res.text
data = res.json()

assert data["json"]["name"]    == "new-repo"
assert data["json"]["private"] == True
assert data["headers"]["Authorization"] == "Bearer ghp_test_token_abc123"

# ── 6. Verify logs were written automatically ──────────────────────────────
print("\n6. Verify IntegrationLogs were created automatically")
res = client.get(f"/api/integrations/{integration_id}/logs")
print("Status:", res.status_code)
assert res.status_code == 200, res.text
logs_data = res.json()
print("Logs:", logs_data)

logs = logs_data["logs"]
assert len(logs) >= 2, f"Expected at least 2 logs, got {len(logs)}"

methods   = [l["method"]   for l in logs]
endpoints = [l["endpoint"] for l in logs]

assert "GET"  in methods
assert "POST" in methods
assert "List repos"   in endpoints, "GET should match documented endpoint description"
assert "Create repo"  in endpoints, "POST should match documented endpoint description"

for log in logs:
    assert log["agent_id"]       == agent_id
    assert log["integration_id"] == integration_id
    assert log["status_code"]    == 200
    assert log["duration_ms"]    >= 0

print("\n✅ ALL TESTS PASSED — Multi-credential proxy flow verified.")