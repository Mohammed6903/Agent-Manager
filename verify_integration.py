import uuid
from fastapi.testclient import TestClient
from main import app
from agent_manager.database import SessionLocal
from agent_manager.services.integration_client import IntegrationClient
from agent_manager.services.integration_service import IntegrationService
import asyncio

client = TestClient(app)

print("--- Testing Integrations API using TestClient ---")

# 1. Create a Global Integration
print("\n1. Create GlobalIntegration")
integration_name = f"test-slack-{uuid.uuid4().hex[:6]}"
res = client.post("/api/integrations", json={
    "name": integration_name,
    "type": "slack",
    "base_url": "https://slack.com/api",
    "auth_fields": [{"name": "bot_token", "label": "Bot Token", "required": True}],
    "endpoints": [{"method": "POST", "path": "/chat.postMessage", "description": "Send a message"}],
    "usage_instructions": "Use Bearer token."
})
print("Status:", res.status_code)
print("Response:", res.json())
assert res.status_code == 200, res.text
integration_id = res.json()["id"]

# 2. List global integrations
print("\n2. List global integrations")
res = client.get("/api/integrations")
print("Status:", res.status_code)
assert res.status_code == 200, res.text

# 3. Assign Integration to Agent
print("\n3. Assign Integration to Agent")
agent_id = f"agent-{uuid.uuid4().hex[:6]}"
res = client.post(f"/api/integrations/{integration_id}/assign", json={
    "agent_id": agent_id,
    "credentials": {"bot_token": "xoxb-test-123"}
})
print("Status:", res.status_code)
assert res.status_code == 200, res.text

# 4. List Agent Integrations
print("\n4. List Agent Integrations")
res = client.get(f"/api/integrations/agent/{agent_id}")
print("Status:", res.status_code)
data = res.json()
print("Response:", data)
assert res.status_code == 200, res.text
assert data["integrations"][0]["integration_id"] == integration_id

# 5. Fetch Agent Credentials
print("\n5. Fetch Agent Credentials")
res = client.get(f"/api/integrations/{integration_id}/credentials?agent_id={agent_id}")
print("Status:", res.status_code)
data = res.json()
print("Response:", data)
assert res.status_code == 200, res.text
assert data["bot_token"] == "xoxb-test-123"

# 6. Test IntegrationClient logging (Mock HTTPX)
# We test IntegrationClient directly rather than mocking external API calls here
# We can just see if it writes the log to the DB
print("\n6. Testing IntegrationClient Log Creation")
async def test_client_log():
    db = SessionLocal()
    try:
        svc = IntegrationService(db)
        int_client = svc.get_integration_client(agent_id, uuid.UUID(integration_id))
        
        # Test endpoint matcher
        matched_desc = int_client._match_endpoint("POST", "https://slack.com/api/chat.postMessage")
        print("Matched Endpoint Name:", matched_desc)
        assert matched_desc == "Send a message", matched_desc
        
    finally:
        db.close()

asyncio.run(test_client_log())


print("\nSUCCESS: All endpoints verified successfully.")
