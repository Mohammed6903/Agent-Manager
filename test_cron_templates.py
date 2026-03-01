import httpx
import uuid
from typing import Dict, Any
import time

BASE_URL = "http://127.0.0.1:8000"
USER_ID = f"test_owner_{uuid.uuid4().hex[:8]}"
OTHER_USER_ID = f"test_other_{uuid.uuid4().hex[:8]}"

def request(method: str, path: str, params: Dict[str, Any] = None, json: Dict[str, Any] = None):
    url = f"{BASE_URL}{path}"
    print(f"\n[{method}] {path}")
    response = httpx.request(method, url, params=params, json=json)
    try:
        data = response.json()
        print(f"Status: {response.status_code}")
        print(data)
        return response.status_code, data
    except Exception as e:
        print(f"Status: {response.status_code}")
        print(response.text)
        return response.status_code, None
        
def run_tests():
    # 0. Create an integration
    int_payload = {
        "name": f"notion_test_{uuid.uuid4().hex[:6]}",
        "type": "notion",
        "base_url": "https://api.notion.com/v1",
        "auth_fields": [],
        "endpoints": [
            {"method": "GET", "path": "/users", "description": "List all users"}
        ],
        "usage_instructions": "This is a test usage."
    }
    status, data = request("POST", "/api/integrations", json=int_payload)
    if status == 201 or status == 200:
        int_id = data["id"]
    else:
        status, data = request("GET", "/api/integrations")
        int_id = data[0]["id"]
        
    print(f"Using Global Integration ID: {int_id}")

    # 1. Create a template
    payload = {
        "name": "Daily Notion Report",
        "description": "Sends a daily report to a notion database",
        "is_public": False,
        "required_integrations": [int_id],
        "variables": [
             {"key": "database_id", "label": "Notion DB ID", "required": True},
             {"key": "time_of_day", "label": "Time (e.g. 09:00)", "required": True, "default": "09:00"}
        ],
        "schedule_kind": "cron",
        "schedule_expr": "0 9 * * *",
        "schedule_human": "Every day at 9 AM",
        "payload_message": "Fetch issues and append to Notion DB: {database_id}",
        "pipeline_template": {
            "tasks": [
                {
                    "name": "Fetch Notion DB",
                    "description": "action=notion.Database.query db={database_id}",
                    "status": "pending",
                    "integrations": ["notion"],
                    "context_sources": []
                }

            ],
            "global_integrations": ["notion"],
            "global_context_sources": []
        }
    }
    
    status, data = request("POST", "/api/cron-templates", params={"user_id": USER_ID}, json=payload)
    assert status == 201
    template_id = data["id"]
    
    # 2. Get the template
    status, data = request("GET", f"/api/cron-templates/{template_id}", params={"user_id": USER_ID})
    assert status == 200
    assert data["name"] == "Daily Notion Report"
    
    # 3. List templates (owner should see it)
    status, data = request("GET", "/api/cron-templates", params={"user_id": USER_ID})
    assert status == 200
    assert len(data) >= 1
    
    # 4. List templates (other user should NOT see it, it is private)
    status, data = request("GET", "/api/cron-templates", params={"user_id": OTHER_USER_ID})
    assert status == 200
    assert not any(t["id"] == template_id for t in data)
    
    # 5. Get template (other user should be forbidden)
    status, data = request("GET", f"/api/cron-templates/{template_id}", params={"user_id": OTHER_USER_ID})
    assert status == 403
    
    # 6. Make public
    status, data = request("PATCH", f"/api/cron-templates/{template_id}", params={"user_id": USER_ID}, json={"is_public": True})
    assert status == 200
    
    # 7. List templates (other user SHOULD see it now)
    status, data = request("GET", "/api/cron-templates", params={"user_id": OTHER_USER_ID})
    assert status == 200
    assert any(t["id"] == template_id for t in data)
    
    # 8. Instantiate template (missing variables)
    inst_payload = {
        "agent_id": "test_agent_1",
        "user_id": USER_ID,
        "session_id": "sess_1",
        "variable_values": {} # missing database_id
    }
    status, data = request("POST", f"/api/cron-templates/{template_id}/instantiate", json=inst_payload)
    assert status == 400
    
    # 8.5 Instantiate template (agent missing integrations)
    inst_payload["variable_values"] = {"database_id": "abc123xyz"}
    status, data = request("POST", f"/api/cron-templates/{template_id}/instantiate", json=inst_payload)
    assert status == 400
    assert "Integration assigned" in data["detail"] or "integration assigned to it" in data["detail"]

    # 8.6 Assign integration to agent
    status, _ = request("POST", f"/api/integrations/{int_id}/assign", json={
        "agent_id": "test_agent_1",
        "credentials": {}
    })
    assert status == 200

    # 9. Instantiate template (successful)
    status, data = request("POST", f"/api/cron-templates/{template_id}/instantiate", json=inst_payload)
    assert status == 201
    job_id = data["job_id"]
    print(f"Instantiated Cron Job ID: {job_id}")
    
    #     not returned as a separate field — verify substitution via payload_message.
    status, data = request("GET", f"/api/crons/{job_id}")
    assert status == 200
    assert "Fetch issues and append to Notion DB: abc123xyz" in data["payload_message"]
    assert "### notion_test_" in data["payload_message"]
    assert "## 1. ASSIGNED INTEGRATIONS (UTMOST PRIORITY)" in data["payload_message"]
    assert "## 4. Workspace Bridge" in data["payload_message"]
    assert "action=notion.Database.query db=abc123xyz" in data["payload_message"]
    
    # 11. Delete template as non-owner (Forbidden)
    status, data = request("DELETE", f"/api/cron-templates/{template_id}", params={"user_id": OTHER_USER_ID})
    assert status == 403
    
    # 12. Delete template as owner
    status, data = request("DELETE", f"/api/cron-templates/{template_id}", params={"user_id": USER_ID})
    assert status == 204
    
    # 13. Verify deletion
    status, data = request("GET", f"/api/cron-templates/{template_id}", params={"user_id": USER_ID})
    assert status == 404
    
    print("\n✅ All Cron Template tests passed!")

if __name__ == "__main__":
    time.sleep(1) # wait for server
    run_tests()
