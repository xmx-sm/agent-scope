"""用户菜单个性化：排序与隐藏。"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import UserMenuPref

LOCKED_KEYS = {"menu.personalize"}


def _parse(raw: str | None) -> dict[str, Any]:
    """内部辅助函数：_parse。
    参数：raw。
    """
    try:
        data = json.loads(raw or "{}")
    except (ValueError, TypeError):
        data = {}
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    hidden = data.get("hidden") if isinstance(data.get("hidden"), list) else []
    return {
        "order": {
            str(key): [str(item) for item in value if isinstance(item, str)]
            for key, value in order.items()
            if isinstance(value, list)
        },
        "hidden": [str(item) for item in hidden if isinstance(item, str)],
    }


async def async_get_prefs(params: dict) -> dict[str, Any]:
    """读取菜单个性化

    参数：session / user_id
    """
    session: AsyncSession = params["session"]
    row = await session.get(UserMenuPref, params["user_id"])
    if row is None:
        return {"order": {}, "hidden": []}
    return _parse(row.config_data)


async def async_save_prefs(params: dict) -> dict[str, Any]:
    """保存菜单个性化

    参数：session / user_id / data
    """
    session: AsyncSession = params["session"]
    data: dict = params["data"]
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    hidden = data.get("hidden") if isinstance(data.get("hidden"), list) else []
    hidden = [str(item) for item in hidden if isinstance(item, str) and item not in LOCKED_KEYS]
    cleaned = {
        "order": {
            str(key): [str(item) for item in value if isinstance(item, str)]
            for key, value in order.items()
            if isinstance(value, list)
        },
        "hidden": sorted(set(hidden)),
    }
    if not cleaned["order"] and not cleaned["hidden"]:
        raise ApiError("个性化配置为空")

    row = await session.get(UserMenuPref, params["user_id"])
    if row is None:
        row = UserMenuPref(user_id=params["user_id"], config_data="{}")
        session.add(row)
    row.config_data = json.dumps(cleaned, ensure_ascii=False)
    await session.commit()
    return cleaned


async def async_reset_prefs(params: dict) -> None:
    """重置菜单个性化

    参数：session / user_id
    """
    session: AsyncSession = params["session"]
    row = await session.get(UserMenuPref, params["user_id"])
    if row is not None:
        await session.delete(row)
        await session.commit()
