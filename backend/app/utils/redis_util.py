"""Redis 探活与客户端工厂：Redis 不可用时快速降级，不阻塞启动。"""

import asyncio
import time

from redis import asyncio as aioredis

from app.core.config import settings

_PROBE_TIMEOUT = 1.0
_PROBE_TTL = 60.0
_probe_cache: tuple[float, bool] | None = None
_client: aioredis.Redis | None = None


async def async_redis_reachable(timeout: float = _PROBE_TIMEOUT, force: bool = False) -> bool:
    global _probe_cache
    now = time.monotonic()
    if not force and _probe_cache is not None and _probe_cache[0] > now:
        return _probe_cache[1]

    reachable = False
    writer = None
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.redis_host, settings.redis_port), timeout
        )
        reachable = True
    except (OSError, asyncio.TimeoutError):
        reachable = False
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass
    _probe_cache = (now + _PROBE_TTL, reachable)
    return reachable


async def async_create_redis_client(force: bool = False) -> aioredis.Redis | None:
    global _probe_cache
    if not await async_redis_reachable(force=force):
        return None
    client = aioredis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        decode_responses=True,
        socket_connect_timeout=2,
    )
    try:
        await asyncio.wait_for(client.ping(), timeout=3.0)
    except Exception:  # noqa: BLE001
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001
            pass
        _probe_cache = (time.monotonic() + _PROBE_TTL, False)
        return None
    return client


async def async_get_redis_client(force: bool = False) -> aioredis.Redis | None:
    """进程级单例；Redis 不可用返回 None（限流自动降级为进程内）。"""
    global _client
    if _client is None:
        _client = await async_create_redis_client(force=force)
    return _client


async def async_close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:  # noqa: BLE001
            pass
        _client = None
