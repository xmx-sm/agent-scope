"""团队权限视图。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.access.permissions.evaluate import async_permission_detail
from app.services.account.user.tree import async_descendants


async def async_team_permissions(params: dict) -> list[dict[str, Any]]:
    """查看直属下级权限概览

    参数：session / viewer
    """
    session: AsyncSession = params["session"]
    viewer: User = params["viewer"]
    users = await async_descendants({"session": session, "user_id": viewer.id})
    result = []
    for user in users:
        detail = await async_permission_detail({"session": session, "user": user})
        result.append(
            {
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname,
                "role": user.role,
                "is_active": user.is_active,
                "permissions": detail["effective"],
                "shrinkable": detail["shrinkable"],
                "temp_grants": detail["temp_grants"],
            }
        )
    return result
