import ijson
import json

data = {
  "agent:garage69ae817f5adfffd952906d9477a581:openai-user:garage69ae817f5adfffd952906d9477a581:mohammed": {
    "sessionId": "1742e6e8-9d8e-4322-8c2a-a4502f727883"
  }
}

with open("test.json", "w") as f:
    json.dump(data, f)

target_session_id = None
with open("test.json", "rb") as file_obj:
    for key, meta in ijson.kvitems(file_obj, ""):
        print(f"Key: {key}")
        if key == "agent:garage69ae817f5adfffd952906d9477a581:openai-user:garage69ae817f5adfffd952906d9477a581:mohammed":
            target_session_id = meta.get("sessionId")
            break
print("Found:", target_session_id)
