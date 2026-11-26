"""运行资源配置快照：更新后本进程即时失效，并保留短 TTL 兜底。"""

import asyncio
import json
import logging
import time
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import SystemConfig
from app.services.config.meta import CONFIG_BY_KEY

logger = logging.getLogger(__name__)
_CACHE_TTL_SECONDS = 5.0
_defaults = {
    key: item["value"]
    for key, item in CONFIG_BY_KEY.items()
    if key.startswith("runtime.")
}
_cache: dict[str, Any] | None = None
_cache_at = 0.0
_lock = asyncio.Lock()


def invalidate_runtime_config() -> None:
    """让下一次准入读取最新配置。"""
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


async def async_get_runtime_config() -> dict[str, Any]:
    """读取运行资源配置；数据库异常时使用安全默认值。"""
    global _cache, _cache_at
    now = time.monotonic()
    async with _lock:
        if _cache is not None and now - _cache_at < _CACHE_TTL_SECONDS:
            return dict(_cache)
        values = dict(_defaults)
        try:
            async with AsyncSessionLocal() as session:
                rows = (
                    await session.execute(
                        select(SystemConfig).where(SystemConfig.key.in_(values))
                    )
                ).scalars().all()
            for row in rows:
                try:
                    values[row.key] = json.loads(row.value)
                except (ValueError, TypeError):
                    logger.warning("运行配置 %s 的值不是合法 JSON，使用默认值", row.key)
        except Exception:
            logger.exception("读取运行配置失败，使用默认值")
        _cache = values
        _cache_at = now
        return dict(values)
