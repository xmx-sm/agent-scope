"""Agent 用量统计。"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentConversation, AgentMessage, AgentModelCall, User


async def async_stats(params: dict) -> dict[str, Any]:
    """参数：session / user_id（None=全平台）/ days"""
    session: AsyncSession = params["session"]
    user_id = params.get("user_id")
    days = max(1, min(int(params.get("days") or 7), 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    msg_conditions = []
    if user_id:
        msg_conditions.append(AgentConversation.user_id == user_id)
    msg_conditions.append(AgentMessage.created_at >= since)
    conv_count = (
        await session.execute(
            select(func.count()).select_from(AgentConversation).where(
                AgentConversation.user_id == user_id
            )
            if user_id
            else select(func.count()).select_from(AgentConversation)
        )
    ).scalar_one()
    msg_row = (
        await session.execute(
            select(
                func.count(AgentMessage.id),
                func.coalesce(func.sum(AgentMessage.input_tokens), 0),
                func.coalesce(func.sum(AgentMessage.output_tokens), 0),
                func.coalesce(func.sum(AgentMessage.cache_input_tokens), 0),
            )
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .where(*msg_conditions)
        )
    ).one()

    call_conditions = [AgentModelCall.created_at >= since]
    if user_id:
        call_conditions.append(AgentModelCall.user_id == user_id)
    rows = (
        await session.execute(select(AgentModelCall).where(*call_conditions))
    ).scalars().all()

    by_model: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    by_user: dict[str, dict] = {}
    by_conversation: dict[str, dict] = {}
    for row in rows:
        model = by_model.setdefault(
            row.model_name, {"model": row.model_name, "calls": 0, "input_tokens": 0,
                             "output_tokens": 0, "cache_input_tokens": 0}
        )
        model["calls"] += row.calls
        model["input_tokens"] += row.input_tokens
        model["output_tokens"] += row.output_tokens
        model["cache_input_tokens"] += row.cache_input_tokens

        day = row.created_at.strftime("%Y-%m-%d") if row.created_at else "unknown"
        daily = by_day.setdefault(day, {"date": day, "calls": 0, "input_tokens": 0,
                                        "output_tokens": 0, "cache_input_tokens": 0})
        daily["calls"] += row.calls
        daily["input_tokens"] += row.input_tokens
        daily["output_tokens"] += row.output_tokens
        daily["cache_input_tokens"] += row.cache_input_tokens

        if row.conversation_id:
            conv = by_conversation.setdefault(
                row.conversation_id, {"conversation_id": row.conversation_id, "calls": 0,
                                      "tokens": 0}
            )
            conv["calls"] += row.calls
            conv["tokens"] += row.input_tokens + row.output_tokens

        if row.user_id:
            u = by_user.setdefault(
                row.user_id, {"user_id": row.user_id, "calls": 0, "input_tokens": 0,
                              "output_tokens": 0, "cache_input_tokens": 0}
            )
            u["calls"] += row.calls
            u["input_tokens"] += row.input_tokens
            u["output_tokens"] += row.output_tokens
            u["cache_input_tokens"] += row.cache_input_tokens

    user_names = {}
    if by_user:
        users = (
            await session.execute(select(User).where(User.id.in_(list(by_user.keys()))))
        ).scalars().all()
        user_names = {u.id: (u.nickname or u.username) for u in users}
    for item in by_user.values():
        item["user_name"] = user_names.get(item["user_id"], item["user_id"])

    total_calls = sum(item["calls"] for item in by_model.values())
    total_input = sum(item["input_tokens"] for item in by_model.values())
    total_output = sum(item["output_tokens"] for item in by_model.values())
    total_cache = sum(item["cache_input_tokens"] for item in by_model.values())

    return {
        "days": days,
        "scope": "global" if not user_id else "user",
        "totals": {
            "conversations": conv_count,
            "messages": msg_row[0],
            "calls": total_calls,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_input_tokens": total_cache,
            "total_tokens": total_input + total_output,
            "message_input_tokens": int(msg_row[1]),
            "message_output_tokens": int(msg_row[2]),
            "message_cache_input_tokens": int(msg_row[3]),
        },
        "by_model": sorted(by_model.values(), key=lambda x: x["input_tokens"] + x["output_tokens"], reverse=True),
        "by_day": sorted(by_day.values(), key=lambda x: x["date"]),
        "by_user": sorted(by_user.values(), key=lambda x: x["input_tokens"] + x["output_tokens"], reverse=True),
        "by_conversation": sorted(by_conversation.values(), key=lambda x: x["tokens"], reverse=True)[:20],
    }
