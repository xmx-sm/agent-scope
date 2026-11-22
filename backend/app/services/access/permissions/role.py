"""角色权限读取与矩阵维护。"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.permissions import (
    ALL_PERMISSION_KEYS,
    ASSIGNABLE_PERMISSION_KEYS,
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    ROLES,
)
from app.models import RolePermission


async def async_role_permissions(params: dict) -> list[str]:
    """参数：session / role"""
    session: AsyncSession = params["session"]
    role: str = params["role"]
    row = await session.get(RolePermission, role)
    if row is None:
        return list(DEFAULT_ROLE_PERMISSIONS.get(role, []))
    try:
        return list(json.loads(row.permissions))
    except (ValueError, TypeError):
        return list(DEFAULT_ROLE_PERMISSIONS.get(role, []))


async def async_list_permissions(params: dict) -> dict:
    """参数：session"""
    session: AsyncSession = params["session"]
    assignable = [item for item in PERMISSIONS if not item.get("super_only")]
    roles = []
    for role in ROLES:
        permissions = (
            list(ALL_PERMISSION_KEYS)
            if role == "super_admin"
            else await async_role_permissions({"session": session, "role": role})
        )
        roles.append(
            {
                "role": role,
                "permissions": permissions,
                "editable": role != "super_admin",
            }
        )
    return {
        "permissions": assignable,
        "all_permissions": PERMISSIONS,
        "roles": roles,
    }


async def async_update_permissions(params: dict) -> dict:
    """参数：session / role / permissions"""
    session: AsyncSession = params["session"]
    role: str = params["role"]
    permissions: list[str] = params["permissions"]
    if role not in ROLES:
        raise ApiError("无效的角色")
    if role == "super_admin":
        raise ApiError("超级管理员权限固定为全部，不可修改")
    valid = set(ASSIGNABLE_PERMISSION_KEYS)
    cleaned = sorted({item for item in permissions if item in valid})
    row = await session.get(RolePermission, role)
    if row is None:
        row = RolePermission(role=role, permissions=json.dumps(cleaned))
        session.add(row)
    else:
        row.permissions = json.dumps(cleaned)
    await session.commit()
    return {"role": role, "permissions": cleaned}
