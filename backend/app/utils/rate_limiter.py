"""滑动窗口限流：优先 Redis（多实例共享），不可用时降级进程内。"""

import time
from typing import Any

from redis import asyncio as aioredis

from app.utils.redis_util import async_get_redis_client

_MEM_MAX_KEYS = 20000


class RateLimiter:
    def __init__(self) -> None:
        self._mem_store: dict[str, list[float]] = {}
        self.last_backend = "memory"

    async def _client(self) -> aioredis.Redis | None:
        return await async_get_redis_client()

    def _mem_check(self, key: str, max_requests: int, window_seconds: int) -> dict[str, Any]:
        now = time.time()
        window_start = now - window_seconds
        arr = [t for t in self._mem_store.get(key, []) if t > window_start]
        allowed = len(arr) < max_requests
        if allowed:
            arr.append(now)
        self._mem_store[key] = arr
        if len(self._mem_store) > _MEM_MAX_KEYS:
            for k in [k for k, v in self._mem_store.items() if not v][
                : len(self._mem_store) - _MEM_MAX_KEYS
            ]:
                self._mem_store.pop(k, None)
        self.last_backend = "memory"
        return {
            "allowed": allowed,
            "remaining": max(0, max_requests - len(arr)) if allowed else 0,
            "reset_at": int(now + window_seconds),
            "current": len(arr),
            "max": max_requests,
        }

    async def check(self, key: str, max_requests: int, window_seconds: int) -> dict[str, Any]:
        client = await self._client()
        if client is not None:
            try:
                now = time.time()
                window_start = now - window_seconds
                pipe = client.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                pipe.zadd(key, {f"{now}": now})
                pipe.expire(key, window_seconds)
                results = await pipe.execute()
                current = int(results[1])
                allowed = current < max_requests
                self.last_backend = "redis"
                return {
                    "allowed": allowed,
                    "remaining": max(0, max_requests - current - 1) if allowed else 0,
                    "reset_at": int(now + window_seconds),
                    "current": current + 1 if allowed else current,
                    "max": max_requests,
                }
            except Exception:  # noqa: BLE001 - Redis 故障时降级，不放行
                pass
        return self._mem_check(key, max_requests, window_seconds)

    async def clear(self, key: str) -> None:
        self._mem_store.pop(key, None)
        client = await self._client()
        if client is not None:
            try:
                await client.delete(key)
            except Exception:  # noqa: BLE001
                pass

    async def list_buckets(self, prefix: str = "rl:", limit: int = 50) -> list[str]:
        client = await self._client()
        if client is not None:
            try:
                keys: list[str] = []
                async for key in client.scan_iter(match=f"{prefix}*", count=200):
                    keys.append(key)
                    if len(keys) >= limit:
                        break
                return keys
            except Exception:  # noqa: BLE001
                pass
        return [key for key in self._mem_store if key.startswith(prefix)][:limit]


rate_limiter = RateLimiter()
