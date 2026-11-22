"""系统配置读写。

统一约定：服务层函数只接收一个字典参数，键名见各函数文档。
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import SystemConfig
from app.services.config.meta import CONFIG_BY_KEY


async def async_get_config(params: dict) -> Any:
    """读取配置。

    参数：session / key / default
    """
    session: AsyncSession = params["session"]
    key: str = params["key"]
    default = params.get("default")
    row = await session.get(SystemConfig, key)
    if row is None:
        return default if default is not None else CONFIG_BY_KEY.get(key, {}).get("value", default)
    try:
        return json.loads(row.value)
    except (ValueError, TypeError):
        return row.value


async def async_list_configs(params: dict) -> list[dict[str, Any]]:
    """参数：session"""
    session: AsyncSession = params["session"]
    rows = (
        await session.execute(select(SystemConfig).order_by(SystemConfig.key))
    ).scalars().all()
    result = []
    for row in rows:
        try:
            value = json.loads(row.value)
        except (ValueError, TypeError):
            value = row.value
        meta = CONFIG_BY_KEY.get(row.key, {})
        result.append(
            {
                "key": row.key,
                "value": value,
                "label": row.label,
                "description": row.description,
                "value_type": row.value_type,
                "group": meta.get("group", "其他"),
                "default": meta.get("value"),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )
    result.sort(key=lambda item: (item["group"], item["key"]))
    return result


async def async_update_config(params: dict) -> dict:
    """参数：session / key / value / operator_id"""
    session: AsyncSession = params["session"]
    key: str = params["key"]
    value = params["value"]
    operator_id: str = params["operator_id"]

    row = await session.get(SystemConfig, key)
    if row is None:
        raise ApiError("配置项不存在", code=404)

    expected = row.value_type
    try:
        if expected == "bool":
            if not isinstance(value, bool):
                raise ValueError
        elif expected == "int":
            value = int(value)
        elif expected == "string":
            if not isinstance(value, str):
                raise ValueError
        elif expected == "json":
            json.dumps(value)
        else:
            raise ValueError
    except (ValueError, TypeError):
        raise ApiError(f"配置 {key} 的值类型应为 {expected}")

    row.value = json.dumps(value, ensure_ascii=False)
    row.updated_by = operator_id
    await session.commit()
    await session.refresh(row)
    return {
        "key": row.key,
        "value": value,
        "label": row.label,
        "description": row.description,
        "value_type": row.value_type,
    }


async def async_reset_config(params: dict) -> dict:
    """参数：session / key / operator_id"""
    key: str = params["key"]
    meta = CONFIG_BY_KEY.get(key)
    if meta is None:
        raise ApiError("该配置项没有默认值可恢复", code=404)
    return await async_update_config(
        {
            "session": params["session"],
            "key": key,
            "value": meta["value"],
            "operator_id": params["operator_id"],
        }
    )
