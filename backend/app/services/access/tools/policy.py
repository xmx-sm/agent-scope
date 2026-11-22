"""新用户 AI 工具默认策略。"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.tools import TOOL_GROUPS, is_valid
from app.models import ToolPolicy, User, UserToolMode, UserToolPermission


async def _async_get_row(session: AsyncSession) -> ToolPolicy | None:
    return await session.get(ToolPolicy, 1)


async def async_get_policy(params: dict) -> dict[str, Any]:
    """参数：session"""
    session: AsyncSession = params["session"]
    row = await _async_get_row(session)
    if row is None:
        return {"new_user_mode": "all", "default_grants": []}
    try:
        grants = json.loads(row.default_grants or "[]")
    except (ValueError, TypeError):
        grants = []
    return {"new_user_mode": row.new_user_mode, "default_grants": grants}


async def async_defaults_view(params: dict) -> dict[str, Any]:
    """参数：session，返回策略 + 带 granted 标记的工具目录。"""
    session: AsyncSession = params["session"]
    policy = await async_get_policy({"session": session})
    granted = {(item.get("group"), item.get("tool") or "") for item in policy["default_grants"]}
    groups = []
    for group in TOOL_GROUPS:
        group_granted = (group["name"], "") in granted
        tools = [
            {
                **tool,
                "granted": group_granted or (group["name"], tool["name"]) in granted,
            }
            for tool in group["tools"]
        ]
        groups.append({**group, "granted": group_granted, "tools": tools})
    return {"new_user_mode": policy["new_user_mode"], "groups": groups}


async def async_set_policy(params: dict) -> dict[str, Any]:
    """参数：session / data"""
    session: AsyncSession = params["session"]
    data: dict = params["data"]
    mode = data.get("new_user_mode") or "all"
    if mode not in ("all", "custom"):
        raise ApiError("new_user_mode 只允许 all/custom")

    items = []
    if mode == "custom":
        seen: set[tuple[str, str]] = set()
        for item in data.get("items") or []:
            group = str(item.get("group") or "")
            tool = str(item.get("tool") or "")
            if not is_valid(group, tool) or (group, tool) in seen:
                continue
            seen.add((group, tool))
            items.append({"group": group, "tool": tool})
        if not items:
            raise ApiError("按清单授权时至少选择一个工具或工具组")

    row = await _async_get_row(session)
    if row is None:
        row = ToolPolicy(id=1, new_user_mode=mode, default_grants="[]")
        session.add(row)
    row.new_user_mode = mode
    row.default_grants = json.dumps(items, ensure_ascii=False)
    await session.commit()
    return await async_get_policy({"session": session})


async def async_apply_new_user(params: dict) -> None:
    """参数：session / user，按默认策略初始化新用户工具权限。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    policy = await async_get_policy({"session": session})

    row = await session.get(UserToolMode, user.id)
    if row is None:
        session.add(UserToolMode(user_id=user.id, mode=policy["new_user_mode"]))
    else:
        row.mode = policy["new_user_mode"]

    if policy["new_user_mode"] == "custom":
        for item in policy["default_grants"]:
            session.add(
                UserToolPermission(
                    user_id=user.id,
                    tool_group=item["group"],
                    tool_name=item.get("tool") or "",
                    enabled=True,
                    granted_by=None,
                )
            )
    await session.commit()
