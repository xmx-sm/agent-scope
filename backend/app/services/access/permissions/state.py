"""用户级权限状态读写。"""

import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserPermissionState
from app.services.access.permissions.common import is_expired, load_list, load_temp


async def async_get_state(params: dict) -> UserPermissionState | None:
    """读取用户权限状态

    参数：session / user_id / create
    """
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    create: bool = bool(params.get("create"))
    state = await session.get(UserPermissionState, user_id)
    if state is None and create:
        state = UserPermissionState(user_id=user_id, granted="[]", shrunk="[]", temp_grants="[]")
        session.add(state)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            state = await session.get(UserPermissionState, user_id)
    return state


def split_state(params: dict) -> tuple[list[str], list[str], list[dict[str, str]]]:
    """拆分权限状态。参数：state。"""
    state: UserPermissionState | None = params.get("state")
    if state is None:
        return [], [], []
    return (
        load_list({"raw": state.granted}),
        load_list({"raw": state.shrunk}),
        [
            item
            for item in load_temp({"raw": state.temp_grants})
            if not is_expired({"value": item["expires_at"]})
        ],
    )


def dump_list(params: dict) -> str:
    """序列化去重排序后的权限数组。参数：values。"""
    return json.dumps(sorted(set(params.get("values") or [])), ensure_ascii=False)
