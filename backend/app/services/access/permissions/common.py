"""权限状态 JSON 与时间工具。"""

import json
from datetime import datetime, timezone

from app.core.deps import ApiError


def _now() -> datetime:
    """内部辅助函数：_now。

    内部时间辅助：当前 UTC 时间。
    """
    return datetime.now(timezone.utc)


def load_list(params: dict) -> list[str]:
    """解析权限字符串数组。参数：raw。"""
    raw = params.get("raw")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(item) for item in data if isinstance(item, str)]
    except (ValueError, TypeError):
        return []


def load_temp(params: dict) -> list[dict[str, str]]:
    """解析临时授权数组。参数：raw。"""
    raw = params.get("raw")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    result = []
    for item in data:
        if isinstance(item, dict) and item.get("permission") and item.get("expires_at"):
            result.append(
                {"permission": str(item["permission"]), "expires_at": str(item["expires_at"])}
            )
    return result


def parse_expire(params: dict) -> datetime:
    """解析并校验临时授权过期时间。参数：value。"""
    value = str(params["value"])
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError("临时授权的过期时间格式不正确")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed <= _now():
        raise ApiError("临时授权的过期时间必须晚于当前时间")
    return parsed


def is_expired(params: dict) -> bool:
    """判断时间字符串是否已过期。参数：value。"""
    value = str(params["value"])
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= _now()
    except ValueError:
        return True
