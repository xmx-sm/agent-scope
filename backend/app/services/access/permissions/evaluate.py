"""有效权限计算。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ALL_PERMISSION_KEYS
from app.models import User
from app.services.access.permissions.role import async_role_permissions
from app.services.access.permissions.state import async_get_state, split_state


async def async_permission_detail(params: dict) -> dict[str, Any]:
    """参数：session / user"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    role_permissions = await async_role_permissions({"session": session, "role": user.role})
    state = await async_get_state({"session": session, "user_id": user.id})
    granted, shrunk, temps = split_state(state)
    base = sorted(set(role_permissions) | set(granted))
    temp_keys = {item["permission"] for item in temps}
    effective = sorted((set(base) - set(shrunk)) | temp_keys)
    if user.role == "super_admin":
        base = list(ALL_PERMISSION_KEYS)
        effective = list(ALL_PERMISSION_KEYS)
        shrunk = []
        temps = []
    return {
        "user_id": user.id,
        "role": user.role,
        "role_permissions": role_permissions,
        "granted": granted,
        "shrunk": shrunk,
        "temp_grants": temps,
        "base": base,
        "effective": effective,
        "shrunk_active": sorted(set(shrunk) & set(base)),
        "shrinkable": sorted((set(base) - temp_keys) - set(shrunk))
        if user.role != "super_admin"
        else [],
    }


async def async_effective_permissions(params: dict) -> list[str]:
    """参数：session / user"""
    user: User = params["user"]
    if user.role == "super_admin":
        return list(ALL_PERMISSION_KEYS)
    return (await async_permission_detail(params))["effective"]
