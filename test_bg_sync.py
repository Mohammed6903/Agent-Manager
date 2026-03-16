import asyncio
import httpx
import time

async def main():
    body = {
      "message": "Testing delay",
      "agent_id": "garage69ae817f5adfffd952906d9477a581",
      "user_id": "mohammed"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:8000/api/chat/completions', json=body, timeout=60.0)
        print("Resp:", resp.status_code)
    
    print("Waiting 5s for bg task...")
    await asyncio.sleep(5)
    
    # Check DB
    from agent_manager.database import SessionLocal
    from agent_manager.models.chat_usage import ChatUsageLog
    with SessionLocal() as db:
        logs = db.query(ChatUsageLog).all()
        print(f"Total logs in DB: {len(logs)}")

if __name__ == "__main__":
    asyncio.run(main())
