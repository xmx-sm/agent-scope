"""会话与消息持久化。"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
import json

from app.models import AgentConversation, AgentMessage


def _load_json(raw: str | None) -> list:
    """内部辅助函数：_load_json。
    参数：raw。
    """
    try:
        data = json.loads(raw or "[]")
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


async def async_list_conversations(params: dict) -> list[dict]:
    """列出当前用户的会话。

        参数：session / user_id / origin / super_agent_id / parent_conversation_id / q / limit。
        """
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    stmt = select(AgentConversation).where(AgentConversation.user_id == user_id)
    origin = params.get("origin")
    if origin == "chat":
        stmt = stmt.where(AgentConversation.origin.is_(None))
    elif origin == "super":
        stmt = stmt.where(AgentConversation.origin.in_(("super_main", "super_sub")))
    elif origin:
        stmt = stmt.where(AgentConversation.origin == origin)
    if params.get("super_agent_id"):
        stmt = stmt.where(AgentConversation.super_agent_id == params["super_agent_id"])
    if params.get("parent_conversation_id"):
        stmt = stmt.where(
            AgentConversation.parent_conversation_id == params["parent_conversation_id"]
        )
    if params.get("q"):
        stmt = stmt.where(AgentConversation.title.contains(str(params["q"])[:100]))
    limit = max(1, min(int(params.get("limit") or 200), 500))
    rows = (
        await session.execute(
            stmt.order_by(AgentConversation.updated_at.desc()).limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "origin": row.origin,
            "super_agent_id": row.super_agent_id,
            "super_agent_member_id": row.super_agent_member_id,
            "parent_conversation_id": row.parent_conversation_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


async def async_create_conversation(params: dict) -> dict:
    """创建会话。

        参数：title / origin / super_agent_id / super_agent_member_id / parent_conversation_id / session / user_id。
        """
    session: AsyncSession = params["session"]
    row = AgentConversation(
        user_id=params["user_id"],
        title=str(params.get("title") or "新会话")[:200],
        origin=params.get("origin"),
        super_agent_id=params.get("super_agent_id"),
        super_agent_member_id=params.get("super_agent_member_id"),
        parent_conversation_id=params.get("parent_conversation_id"),
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
    """读取当前用户拥有的会话。

        参数：session / conversation_id / user_id。
        """
    session: AsyncSession = params["session"]
    row = await session.get(AgentConversation, params["conversation_id"])
    if row is None or row.user_id != params["user_id"]:
        raise ApiError("会话不存在", code=404)
    return row


async def async_delete_conversation(params: dict) -> None:
    """删除会话及其消息。

        参数：session。
        """
    session: AsyncSession = params["session"]
    conv = await async_get_owned(params)
    await session.execute(
        delete(AgentMessage).where(AgentMessage.conversation_id == conv.id)
    )
    await session.delete(conv)
    await session.commit()


async def async_list_messages(params: dict) -> list[dict]:
    """列出会话消息。

        参数：session。
        """
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
            "attachments": _load_json(row.attachments),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def async_save_message(params: dict) -> AgentMessage:
    """保存一条会话消息，并在首条用户消息时自动命名会话。

    参数：
    - session：数据库会话
    - conversation_id：会话 ID
    - role：user / assistant / system / tool
    - content：消息正文
    - reasoning：思考过程
    - tool_events：工具调用事件 JSON 字符串
    - attachments：附件元数据 JSON 字符串
    - input_tokens / output_tokens / cache_input_tokens：模型用量
    """
    session: AsyncSession = params["session"]
    row = AgentMessage(
        conversation_id=params["conversation_id"],
        role=params["role"],
        content=params.get("content") or "",
        reasoning=params.get("reasoning") or "",
        tool_events=params.get("tool_events") or "[]",
        attachments=params.get("attachments") or "[]",
        input_tokens=int(params.get("input_tokens") or 0),
        output_tokens=int(params.get("output_tokens") or 0),
        cache_input_tokens=int(params.get("cache_input_tokens") or 0),
    )
    session.add(row)
    conv = await session.get(AgentConversation, params["conversation_id"])
    if conv is not None and conv.title == "新会话" and params["role"] == "user":
        conv.title = (params.get("content") or "新会话")[:30]
    await session.commit()
    await session.refresh(row)
    return row


async def async_rename_conversation(params: dict) -> dict:
    """重命名会话。

        参数：title / session。
        """
    session: AsyncSession = params["session"]
    conv = await async_get_owned(params)
    title = str(params.get("title") or "").strip()
    if not title:
        raise ApiError("标题不能为空")
    conv.title = title[:200]
    await session.commit()
    return {"id": conv.id, "title": conv.title}


async def async_usage_stats(params: dict) -> dict:
    """统计当前用户会话与 token 用量。

        参数：session / user_id。
        """
    from sqlalchemy import func

    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    conv_count = (
        await session.execute(
            select(func.count()).select_from(AgentConversation).where(
                AgentConversation.user_id == user_id
            )
        )
    ).scalar_one()
    msg_count, input_tokens, output_tokens = (
        await session.execute(
            select(
                func.count(AgentMessage.id),
                func.coalesce(func.sum(AgentMessage.input_tokens), 0),
                func.coalesce(func.sum(AgentMessage.output_tokens), 0),
            )
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .where(AgentConversation.user_id == user_id)
        )
    ).one()
    return {
        "conversations": conv_count,
        "messages": msg_count,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(input_tokens) + int(output_tokens),
    }


async def async_branch_conversation(params: dict) -> dict:
    """从某条消息创建分支会话：复制该消息及之前的消息。"""
    session: AsyncSession = params["session"]
    source = await async_get_owned(
        {"session": session, "user_id": params["user_id"],
         "conversation_id": params["conversation_id"]}
    )
    target = await session.get(AgentMessage, params["message_id"])
    if target is None or target.conversation_id != source.id:
        raise ApiError("消息不存在", code=404)
    rows = (
        await session.execute(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == source.id)
            .order_by(AgentMessage.created_at.asc())
        )
    ).scalars().all()
    branch = AgentConversation(
        user_id=params["user_id"],
        title=f"分支 · {source.title}"[:200],
        origin="branch",
        super_agent_id=source.super_agent_id,
        super_agent_member_id=source.super_agent_member_id,
        parent_conversation_id=source.id,
    )
    session.add(branch)
    await session.flush()
    for row in rows:
        session.add(
            AgentMessage(
                conversation_id=branch.id,
                role=row.role,
                content=row.content,
                reasoning=row.reasoning,
                tool_events=row.tool_events,
                attachments=row.attachments,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cache_input_tokens=row.cache_input_tokens,
            )
        )
        if row.id == target.id:
            break
    await session.commit()
    await session.refresh(branch)
    return {
        "id": branch.id,
        "title": branch.title,
        "origin": branch.origin,
        "parent_conversation_id": branch.parent_conversation_id,
    }
