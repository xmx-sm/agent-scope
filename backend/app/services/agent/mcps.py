"""用户 MCP 配置管理。"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import User, UserMcp


def _public(row: UserMcp) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "mcp_type": row.mcp_type,
        "url": row.url,
        "command": row.command,
        "args": json.loads(row.args or "[]"),
        "env": json.loads(row.env or "{}"),
        "is_active": row.is_active,
    }


async def async_list(params: dict) -> list[dict]:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserMcp).where(UserMcp.user_id == user.id).order_by(UserMcp.name)
        )
    ).scalars().all()
    return [_public(row) for row in rows]


async def async_save(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    data: dict = params["data"]
    name = str(data.get("name") or "").strip()
    if not name:
        raise ApiError("MCP 名称不能为空")
    mcp_type = str(data.get("mcp_type") or "http")
    if mcp_type not in ("http", "stdio"):
        raise ApiError("MCP 类型只支持 http / stdio")
    if mcp_type == "http" and not str(data.get("url") or "").strip():
        raise ApiError("HTTP MCP 需要填写 URL")
    if mcp_type == "stdio" and not str(data.get("command") or "").strip():
        raise ApiError("stdio MCP 需要填写 command")

    row = None
    if data.get("id"):
        row = await session.get(UserMcp, data["id"])
        if row is None or row.user_id != user.id:
            raise ApiError("MCP 不存在", code=404)
    else:
        row = (
            await session.execute(
                select(UserMcp).where(UserMcp.user_id == user.id, UserMcp.name == name)
            )
        ).scalar_one_or_none()
    if row is None:
        row = UserMcp(user_id=user.id, name=name)
        session.add(row)
    row.name = name
    row.mcp_type = mcp_type
    row.url = str(data.get("url") or "")
    row.command = str(data.get("command") or "")
    row.args = json.dumps(data.get("args") or [], ensure_ascii=False)
    row.env = json.dumps(data.get("env") or {}, ensure_ascii=False)
    row.is_active = bool(data.get("is_active", True))
    await session.commit()
    await session.refresh(row)
    return _public(row)


async def async_delete(params: dict) -> None:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    row = await session.get(UserMcp, params["mcp_id"])
    if row is None or row.user_id != user.id:
        raise ApiError("MCP 不存在", code=404)
    await session.delete(row)
    await session.commit()


async def async_active_servers(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserMcp).where(UserMcp.user_id == user.id, UserMcp.is_active.is_(True))
        )
    ).scalars().all()
    servers = {}
    for row in rows:
        if row.mcp_type == "http":
            servers[row.name] = {"type": "http", "url": row.url}
        else:
            servers[row.name] = {
                "type": "stdio",
                "command": row.command,
                "args": json.loads(row.args or "[]"),
                "env": json.loads(row.env or "{}"),
            }
    return servers
