"""AI 工具授权、模式切换与逐级收窄。"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.tools import GROUP_MAP, is_valid
from app.models import User, UserToolMode, UserToolPermission
from app.services.tools.evaluate import async_tool_view
from app.services.user.tree import async_is_descendant


async def _async_set_mode(session: AsyncSession, user_id: str, mode: str) -> None:
    if mode not in ("all", "custom"):
        raise ApiError("tool_mode 只允许 all/custom")
    row = await session.get(UserToolMode, user_id)
    if row is None:
        session.add(UserToolMode(user_id=user_id, mode=mode))
    else:
        row.mode = mode


async def async_set_tools(params: dict) -> dict:
    """超管全量设置：模式 + custom 清单。参数：session / target / data"""
    session: AsyncSession = params["session"]
    target: User = params["target"]
    data: dict = params["data"]
    mode = data.get("mode") or "all"
    if mode not in ("all", "custom"):
        raise ApiError("tool_mode 只允许 all/custom")

    await session.execute(
        delete(UserToolPermission).where(UserToolPermission.user_id == target.id)
    )
    await _async_set_mode(session, target.id, mode)
    if mode == "custom":
        items = data.get("items") or []
        seen: set[tuple[str, str]] = set()
        for item in items:
            group = str(item.get("group") or "")
            tool = str(item.get("tool") or "")
            if not is_valid(group, tool):
                continue
            key = (group, tool)
            if key in seen:
                continue
            seen.add(key)
            session.add(
                UserToolPermission(
                    user_id=target.id,
                    tool_group=group,
                    tool_name=tool,
                    enabled=True,
                    granted_by=None,
                )
            )
        if not seen:
            raise ApiError("按清单授权时至少选择一个工具或工具组")
    await session.commit()
    return await async_tool_view({"session": session, "user": target})


async def async_reset_tools(params: dict) -> dict:
    """超管恢复默认：全部工具、清空所有收窄。参数：session / target"""
    session: AsyncSession = params["session"]
    target: User = params["target"]
    await session.execute(
        delete(UserToolPermission).where(UserToolPermission.user_id == target.id)
    )
    await _async_set_mode(session, target.id, "all")
    await session.commit()
    return await async_tool_view({"session": session, "user": target})


async def async_narrow_tool(params: dict) -> dict:
    """上级/本人收窄工具。参数：session / actor / target_id / group / tool / enabled"""
    session: AsyncSession = params["session"]
    actor: User = params["actor"]
    target_id: str = params["target_id"]
    group: str = str(params.get("group") or "")
    tool: str = str(params.get("tool") or "")
    enabled: bool = bool(params.get("enabled"))

    if not is_valid(group, tool):
        raise ApiError("未知工具或工具组")
    if target_id != actor.id:
        if actor.role == "super_admin":
            pass
        elif not await async_is_descendant(
            {"session": session, "ancestor_id": actor.id, "target_id": target_id}
        ):
            raise ApiError("只能管理自己的下属", code=403)
    target = await session.get(User, target_id)
    if target is None:
        raise ApiError("用户不存在", code=404)

    existing = (
        await session.execute(
            select(UserToolPermission).where(
                UserToolPermission.user_id == target_id,
                UserToolPermission.tool_group == group,
                UserToolPermission.tool_name == tool,
            )
        )
    ).scalar_one_or_none()

    if enabled:
        # 恢复=删除本人收窄行；其他上级的收窄行仍然生效
        if existing is not None and existing.granted_by == actor.id:
            await session.delete(existing)
    else:
        if target_id == actor.id and actor.role == "super_admin":
            raise ApiError("超级管理员无需收缩自己")
        if existing is None:
            session.add(
                UserToolPermission(
                    user_id=target_id,
                    tool_group=group,
                    tool_name=tool,
                    enabled=False,
                    granted_by=actor.id,
                )
            )
        else:
            existing.enabled = False
            existing.granted_by = actor.id
    await session.commit()
    return await async_tool_view({"session": session, "user": target})


async def async_team_tools(params: dict) -> list[dict]:
    """参数：session / viewer，返回下属及工具权限概览。"""
    session: AsyncSession = params["session"]
    viewer: User = params["viewer"]
    from app.services.user.tree import async_descendants

    users = await async_descendants({"session": session, "user_id": viewer.id})
    result = []
    for user in users:
        view = await async_tool_view({"session": session, "user": user})
        result.append(
            {
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname,
                "role": user.role,
                "mode": view["mode"],
                "enabled_count": view["enabled_count"],
                "total_count": view["total_count"],
                "groups": view["groups"],
            }
        )
    return result
