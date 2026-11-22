"""权限状态 JSON 与时间工具。"""

import json
from datetime import datetime, timezone

from app.core.deps import ApiError


def load_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(item) for item in data if isinstance(item, str)]
    except (ValueError, TypeError):
        return []


def load_temp(raw: str | None) -> list[dict[str, str]]:
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_expire(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError("临时授权的过期时间格式不正确")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed <= utc_now():
        raise ApiError("临时授权的过期时间必须晚于当前时间")
    return parsed


def is_expired(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= utc_now()
    except ValueError:
        return True
