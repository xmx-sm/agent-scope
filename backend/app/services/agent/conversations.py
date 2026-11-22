"""会话与消息持久化。"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import AgentConversation, AgentMessage


async def async_list_conversations(params: dict) -> list[dict]:
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    rows = (
        await session.execute(
            select(AgentConversation)
            .where(AgentConversation.user_id == user_id)
            .order_by(AgentConversation.updated_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


async def async_create_conversation(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = AgentConversation(
        user_id=params["user_id"],
        title=str(params.get("title") or "新会话")[:200],
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": row.id,
        "title": row.title,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def async_get_owned(params: dict) -> AgentConversation:
    session: AsyncSession = params["session"]
    row = await session.get(AgentConversation, params["conversation_id"])
    if row is None or row.user_id != params["user_id"]:
        raise ApiError("会话不存在", code=404)
    return row


async def async_delete_conversation(params: dict) -> None:
    session: AsyncSession = params["session"]
    conv = await async_get_owned(params)
    await session.execute(
        delete(AgentMessage).where(AgentMessage.conversation_id == conv.id)
    )
    await session.delete(conv)
    await session.commit()


async def async_list_messages(params: dict) -> list[dict]:
    session: AsyncSession = params["session"]
    conv = await async_get_owned(params)
    rows = (
        await session.execute(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conv.id)
            .order_by(AgentMessage.created_at.asc())
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "reasoning": row.reasoning,
            "tool_events": row.tool_events,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def async_save_message(
    session: AsyncSession,
    *,
    conversation_id: str,
    role: str,
    content: str,
    reasoning: str = "",
    tool_events: str = "[]",
) -> AgentMessage:
    row = AgentMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        reasoning=reasoning,
        tool_events=tool_events,
    )
    session.add(row)
    conv = await session.get(AgentConversation, conversation_id)
    if conv is not None and conv.title == "新会话" and role == "user":
        conv.title = (content or "新会话")[:30]
    await session.commit()
    await session.refresh(row)
    return row
