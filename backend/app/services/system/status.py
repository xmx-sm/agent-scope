"""运行状态响应组装。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.system.monitor import async_system_status
from app.utils.rate_limiter import rate_limiter


async def async_status(params: dict) -> dict:
    """参数：session"""
    session: AsyncSession = params["session"]
    data = await async_system_status({"session": session})
    data["redis"]["rate_limit_backend"] = rate_limiter.last_backend
    data["redis"]["rate_limit_buckets"] = len(
        await rate_limiter.list_buckets(prefix="rl:", limit=10000)
    )
    return data
