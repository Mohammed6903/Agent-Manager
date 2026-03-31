"""Repository for persisted conversation messages."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.conversation_message import ConversationMessage


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_next_sequence(self, session_id: str) -> int:
        max_seq = (
            self.db.query(func.max(ConversationMessage.sequence))
            .filter(ConversationMessage.session_id == session_id)
            .scalar()
        )
        return (max_seq or 0) + 1

    def add_message(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        role: str,
        content: str,
        room_id: Optional[str] = None,
    ) -> ConversationMessage:
        seq = self.get_next_sequence(session_id)
        msg = ConversationMessage(
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            role=role,
            content=content,
            sequence=seq,
            room_id=room_id,
        )
        self.db.add(msg)
        self.db.commit()
        return msg

    def get_history(
        self,
        session_id: str,
        limit: int = 100,
    ) -> List[ConversationMessage]:
        return (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.sequence.asc())
            .limit(limit)
            .all()
        )

    def get_user_sessions(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get recent sessions for a user, with last message preview."""
        query = (
            self.db.query(
                ConversationMessage.session_id,
                func.max(ConversationMessage.created_at).label("last_at"),
                func.count(ConversationMessage.id).label("msg_count"),
            )
            .filter(ConversationMessage.user_id == user_id)
            .group_by(ConversationMessage.session_id)
            .order_by(func.max(ConversationMessage.created_at).desc())
            .limit(limit)
        )
        if agent_id:
            query = query.filter(ConversationMessage.agent_id == agent_id)

        rows = query.all()
        return [
            {"session_id": r.session_id, "last_at": r.last_at, "message_count": r.msg_count}
            for r in rows
        ]
