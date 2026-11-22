"""用户子智能体管理。"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.tools import all_items
from app.models import User, UserSubagent
from app.services.access.tools.evaluate import async_tool_view

_ALLOWED = {item["tool"] for item in all_items()}


def _public(row: UserSubagent) -> dict:
    """内部辅助函数：_public。
    参数：row。
    """
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "system_prompt": row.system_prompt,
        "tools": json.loads(row.tools or "[]"),
        "mode": row.mode,
        "is_active": row.is_active,
    }


async def async_list(params: dict) -> list[dict]:
    """列出用户子智能体。

        参数：session / user。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserSubagent).where(UserSubagent.user_id == user.id).order_by(UserSubagent.name)
        )
    ).scalars().all()
    return [_public(row) for row in rows]


async def async_save(params: dict) -> dict:
    """新建或更新子智能体。

        参数：session / user / data。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    data: dict = params["data"]
    name = str(data.get("name") or "").strip()
    if not name:
        raise ApiError("子智能体名称不能为空")
    if not str(data.get("system_prompt") or "").strip():
        raise ApiError("子智能体必须填写系统提示词")
    tools = [str(item) for item in (data.get("tools") or []) if str(item) in _ALLOWED]
    row = None
    if data.get("id"):
        row = await session.get(UserSubagent, data["id"])
        if row is None or row.user_id != user.id:
            raise ApiError("子智能体不存在", code=404)
    else:
        row = (
            await session.execute(
                select(UserSubagent).where(
                    UserSubagent.user_id == user.id, UserSubagent.name == name
                )
            )
        ).scalar_one_or_none()
    if row is None:
        row = UserSubagent(user_id=user.id, name=name)
        session.add(row)
    row.name = name
    row.description = str(data.get("description") or "")[:500]
    row.system_prompt = str(data.get("system_prompt") or "")
    row.tools = json.dumps(tools, ensure_ascii=False)
    row.mode = str(data.get("mode") or "auto")
    row.is_active = bool(data.get("is_active", True))
    await session.commit()
    await session.refresh(row)
    return _public(row)


async def async_delete(params: dict) -> None:
    """删除子智能体。

        参数：session / user / subagent_id。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    row = await session.get(UserSubagent, params["subagent_id"])
    if row is None or row.user_id != user.id:
        raise ApiError("子智能体不存在", code=404)
    await session.delete(row)
    await session.commit()


async def async_specs(params: dict) -> list[dict]:
    """返回可用于 scope 委派的 spec 列表，工具按用户有效权限过滤。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserSubagent).where(
                UserSubagent.user_id == user.id, UserSubagent.is_active.is_(True)
            )
        )
    ).scalars().all()
    if not rows:
        return []
    view = await async_tool_view({"session": session, "user": user})
    enabled = {
        tool["name"]
        for group in view["groups"]
        for tool in group["tools"]
        if tool["enabled"]
    }
    result = []
    for row in rows:
        tools = [name for name in json.loads(row.tools or "[]") if name in enabled]
        result.append(
            {
                "name": row.name,
                "description": row.description,
                "system_prompt": row.system_prompt,
                "tools": tools,
                "mode": row.mode,
            }
        )
    return result
