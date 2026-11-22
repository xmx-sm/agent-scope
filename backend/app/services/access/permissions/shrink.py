"""权限逐级收缩。"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.permissions import ALL_PERMISSION_KEYS
from app.models import User
from app.services.access.permissions.evaluate import async_permission_detail
from app.services.access.permissions.state import async_get_state
from app.services.account.user.tree import async_is_descendant


async def _async_add_shrink(params: dict) -> list[str]:
    """内部辅助函数：_async_add_shrink。

    参数：session / target / permissions / operator_id
    """
    session: AsyncSession = params["session"]
    target: User = params["target"]
    permissions: list[str] = params["permissions"]
    operator_id: str = params["operator_id"]
    detail = await async_permission_detail({"session": session, "user": target})
    temp_keys = {item["permission"] for item in detail["temp_grants"]}
    current = set(detail["shrunk"])
    added = []
    for permission in permissions:
        if permission not in ALL_PERMISSION_KEYS:
            continue
        if permission in temp_keys:
            raise ApiError(f"权限「{permission}」为超管临时授权，不能被收缩")
        if permission in detail["effective"] and permission not in current:
            current.add(permission)
            added.append(permission)
    if not added:
        raise ApiError("没有可收缩的权限（请选择该用户当前拥有的权限）")

    state = await async_get_state({"session": session, "user_id": target.id, "create": True})
    state.shrunk = json.dumps(sorted(current), ensure_ascii=False)
    state.updated_by = operator_id
    await session.commit()
    return added


async def async_shrink_self(params: dict) -> list[str]:
    """本人收缩自己的权限

    参数：session / user / permissions
    """
    user: User = params["user"]
    if user.role == "super_admin":
        raise ApiError("超级管理员权限固定，无需收缩")
    return await _async_add_shrink(
        {
            "session": params["session"],
            "target": user,
            "permissions": params["permissions"],
            "operator_id": user.id,
        }
    )


async def async_shrink_member(params: dict) -> list[str]:
    """上级收缩下级权限

    参数：session / actor / target_id / permissions
    """
    session: AsyncSession = params["session"]
    actor: User = params["actor"]
    target_id: str = params["target_id"]
    if actor.role == "super_admin":
        raise ApiError("超级管理员请在用户管理中直接调整权限")
    if not await async_is_descendant(
        {"session": session, "ancestor_id": actor.id, "target_id": target_id}
    ):
        raise ApiError("只能收缩自己的下属", code=403)
    target = await session.get(User, target_id)
    if target is None:
        raise ApiError("用户不存在", code=404)
    if target.role == "super_admin":
        raise ApiError("无权收缩超级管理员", code=403)
    return await _async_add_shrink(
        {
            "session": session,
            "target": target,
            "permissions": params["permissions"],
            "operator_id": actor.id,
        }
    )
