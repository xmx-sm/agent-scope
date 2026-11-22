"""用户级权限状态读写。"""

import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserPermissionState
from app.services.access.permissions.common import is_expired, load_list, load_temp


async def async_get_state(params: dict) -> UserPermissionState | None:
    """参数：session / user_id / create"""
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


def split_state(
    state: UserPermissionState | None,
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    if state is None:
        return [], [], []
    return (
        load_list(state.granted),
        load_list(state.shrunk),
        [
            item
            for item in load_temp(state.temp_grants)
            if not is_expired(item["expires_at"])
        ],
    )


def dump_list(values: list[str]) -> str:
    return json.dumps(sorted(set(values)), ensure_ascii=False)
