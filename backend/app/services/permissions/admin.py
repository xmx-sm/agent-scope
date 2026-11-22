"""超管侧用户权限配置。"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.permissions import ALL_PERMISSION_KEYS, ASSIGNABLE_PERMISSION_KEYS, PERMISSIONS
from app.models import User
from app.services.permissions.common import parse_expire
from app.services.permissions.evaluate import async_permission_detail
from app.services.permissions.state import async_get_state
from app.services.user.query import async_get_user_or_404


async def async_admin_set_state(params: dict) -> dict[str, Any]:
    """参数：session / target / granted / shrunk / temp_grants / operator_id"""
    session: AsyncSession = params["session"]
    target: User = params["target"]
    granted = params.get("granted")
    shrunk = params.get("shrunk")
    temp_grants = params.get("temp_grants")
    operator_id: str = params["operator_id"]

    if target.role == "super_admin":
        raise ApiError("超级管理员权限固定为全部，无需设置")

    state = await async_get_state({"session": session, "user_id": target.id, "create": True})

    if granted is not None:
        state.granted = json.dumps(
            sorted({item for item in granted if item in ASSIGNABLE_PERMISSION_KEYS}),
            ensure_ascii=False,
        )
    if shrunk is not None:
        state.shrunk = json.dumps(
            sorted({item for item in shrunk if item in ASSIGNABLE_PERMISSION_KEYS}),
            ensure_ascii=False,
        )
    if temp_grants is not None:
        cleaned: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in temp_grants:
            permission = str(item.get("permission") or "")
            expires_at = str(item.get("expires_at") or "")
            if permission not in ALL_PERMISSION_KEYS or permission in seen:
                continue
            parse_expire(expires_at)
            cleaned.append({"permission": permission, "expires_at": expires_at})
            seen.add(permission)
        state.temp_grants = json.dumps(cleaned, ensure_ascii=False)

    state.updated_by = operator_id
    await session.commit()
    return await async_permission_detail({"session": session, "user": target})


async def async_user_permission_detail(params: dict) -> dict:
    """参数：session / user_id"""
    session: AsyncSession = params["session"]
    target = await async_get_user_or_404(
        {"session": session, "user_id": params["user_id"]}
    )
    detail = await async_permission_detail({"session": session, "user": target})
    detail["catalog"] = PERMISSIONS
    return detail


async def async_set_user_permissions(params: dict) -> dict:
    """参数：session / user_id / data / operator_id"""
    session: AsyncSession = params["session"]
    target = await async_get_user_or_404(
        {"session": session, "user_id": params["user_id"]}
    )
    data: dict = params["data"]
    return await async_admin_set_state(
        {
            "session": session,
            "target": target,
            "granted": data.get("granted"),
            "shrunk": data.get("shrunk"),
            "temp_grants": data.get("temp_grants"),
            "operator_id": params["operator_id"],
        }
    )
