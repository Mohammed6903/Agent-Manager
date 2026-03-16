import asyncio
import httpx
import time

async def main():
    body = {
      "message": "Testing stream delay",
      "agent_id": "garage69ae817f5adfffd952906d9477a581",
      "user_id": "mohammed"
    }
    
    # Pre-count DB logs
    from agent_manager.database import SessionLocal
    from agent_manager.models.chat_usage import ChatUsageLog
    with SessionLocal() as db:
        initial_logs = db.query(ChatUsageLog).count()
        print(f"Initial logs in DB: {initial_logs}")
        
    async with httpx.AsyncClient() as client:
        async with client.stream('POST', 'http://localhost:8000/api/chat', json=body, timeout=60.0) as resp:
            print("Stream status:", resp.status_code)
            async for chunk in resp.aiter_bytes():
                pass
            print("Stream finished.")
    
    print("Waiting 5s for bg task...")
    await asyncio.sleep(5)
    
    with SessionLocal() as db:
        final_logs = db.query(ChatUsageLog).count()
        print(f"Final logs in DB: {final_logs}")

if __name__ == "__main__":
    asyncio.run(main())
