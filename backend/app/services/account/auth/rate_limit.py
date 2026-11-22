"""认证限流：读取配置并执行滑动窗口检查。"""

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.services.config.service import async_get_config
from app.utils.rate_limiter import rate_limiter


async def async_rate_limit(params: dict) -> None:
    """参数：session / key / max_key / window_key / max_default / window_default"""
    session: AsyncSession = params["session"]
    if not await async_get_config({"session": session, "key": "rate_limit_enabled", "default": True}):
        return
    max_requests = int(
        await async_get_config(
            {"session": session, "key": params["max_key"], "default": params["max_default"]}
        )
    )
    window_seconds = int(
        await async_get_config(
            {"session": session, "key": params["window_key"], "default": params["window_default"]}
        )
    )
    result = await rate_limiter.check(
        params["key"], max_requests, window_seconds
    )
    if not result["allowed"]:
        wait = max(1, (result["reset_at"] - int(time.time())) // 60 + 1)
        raise ApiError(f"尝试过于频繁，请约 {wait} 分钟后重试", code=429, status_code=429)
