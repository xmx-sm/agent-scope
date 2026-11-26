"""进程内动态并发名额；限制只影响新准入，不终止存量任务。"""

import asyncio
from contextlib import asynccontextmanager

from app.core.deps import ApiError
from app.utils.runtime_config import async_get_runtime_config

_active: dict[str, int] = {}
_lock = asyncio.Lock()


async def acquire_runtime_slot(
    name: str,
    config_key: str,
    default: int,
    message: str,
) -> None:
    """尝试占用一个动态并发名额。"""
    config = await async_get_runtime_config()
    limit = max(1, int(config.get(config_key, default)))
    async with _lock:
        if _active.get(name, 0) >= limit:
            raise ApiError(message, code=429)
        _active[name] = _active.get(name, 0) + 1


def release_runtime_slot(name: str) -> None:
    """释放并发名额。"""
    current = _active.get(name, 0)
    if current <= 1:
        _active.pop(name, None)
    else:
        _active[name] = current - 1


@asynccontextmanager
async def runtime_slot(
    name: str,
    config_key: str,
    default: int,
    message: str,
):
    """为一次操作维护动态并发名额。"""
    await acquire_runtime_slot(name, config_key, default, message)
    try:
        yield
    finally:
        release_runtime_slot(name)
