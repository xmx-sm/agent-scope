"""AI 工具权限计算。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tools import TOOL_GROUPS
from app.models import User, UserToolMode, UserToolPermission


async def async_get_mode(params: dict) -> str:
    """参数：session / user_id"""
    session: AsyncSession = params["session"]
    row = await session.get(UserToolMode, params["user_id"])
    return (row.mode if row else "all") or "all"


async def async_tool_view(params: dict) -> dict[str, Any]:
    """参数：session / user，返回完整工具目录与该用户生效状态。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    mode = await async_get_mode({"session": session, "user_id": user.id})
    rows = (
        await session.execute(
            select(UserToolPermission).where(UserToolPermission.user_id == user.id)
        )
    ).scalars().all()

    grant_keys = {(r.tool_group, r.tool_name) for r in rows if r.enabled}
    disabled_group = {r.tool_group for r in rows if not r.enabled and not r.tool_name}
    disabled_tool = {(r.tool_group, r.tool_name) for r in rows if not r.enabled and r.tool_name}

    groups = []
    enabled_count = 0
    total_count = 0
    for group in TOOL_GROUPS:
        group_granted = mode == "all" or (group["name"], "") in grant_keys
        tools = []
        for tool in group["tools"]:
            total_count += 1
            granted = group_granted or (group["name"], tool["name"]) in grant_keys
            enabled = (
                granted
                and group["name"] not in disabled_group
                and (group["name"], tool["name"]) not in disabled_tool
            )
            if enabled:
                enabled_count += 1
            tools.append(
                {
                    "name": tool["name"],
                    "label": tool["label"],
                    "description": tool["description"],
                    "granted": granted,
                    "enabled": enabled,
                }
            )
        groups.append(
            {
                "name": group["name"],
                "label": group["label"],
                "description": group["description"],
                "granted": group_granted,
                "enabled": group["name"] not in disabled_group
                and any(t["enabled"] for t in tools),
                "tools": tools,
            }
        )
    return {
        "user_id": user.id,
        "mode": mode,
        "enabled_count": enabled_count,
        "total_count": total_count,
        "groups": groups,
    }
