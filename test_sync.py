import asyncio
from agent_manager.database import SessionLocal
from agent_manager.services.usage_service import UsageService
import logging

logging.basicConfig(level=logging.DEBUG)

async def main():
    agent_id = "garage69ae817f5adfffd952906d9477a581"
    user_id = "mohammed"
    session_key = f"agent:{agent_id}:openai-user:{agent_id}:{user_id}"
    
    with SessionLocal() as db:
        svc = UsageService(gateway=None, db=db)
        await svc.sync_single_session(agent_id, session_key, user_id)
        
        # Check if saved
        from agent_manager.models.chat_usage import ChatUsageLog
        logs = db.query(ChatUsageLog).filter_by(agent_id=agent_id).all()
        print(f"Found {len(logs)} logs")

if __name__ == "__main__":
    asyncio.run(main())
