"""Conversation/message repository — the agent-facing memory API."""

from typing import Any
from uuid import UUID

from sqlmodel import select

from agencyos.memory.db import get_session
from agencyos.memory.models import Conversation, Message


async def create_conversation(user_id: str, title: str, client_id: str | None = None) -> Conversation:
    async with get_session() as s:
        conv = Conversation(user_id=user_id, client_id=client_id, title=title)
        s.add(conv)
        await s.flush()
        return conv


async def append_message(
    conversation_id: UUID,
    *,
    role: str,
    content: dict[str, Any],
    agent_name: str | None = None,
    reasoning: str | None = None,
    tool_calls: dict[str, Any] | None = None,
) -> Message:
    async with get_session() as s:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            agent_name=agent_name,
            content=content,
            reasoning=reasoning,
            tool_calls=tool_calls,
        )
        s.add(msg)
        await s.flush()
        return msg


async def load_thread(conversation_id: UUID, limit: int = 50) -> list[Message]:
    async with get_session() as s:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await s.execute(stmt)
        return list(reversed(result.scalars().all()))
