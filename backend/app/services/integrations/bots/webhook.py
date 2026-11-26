"""机器人 Webhook 数据面。"""

import asyncio
import hashlib
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.deps import ApiError
from app.models import AgentConversation, BotSessionMap, User, UserBot
from app.services.access.permissions.evaluate import async_effective_permissions
from app.services.agent.conversation.chat import async_run_turn
from app.services.integrations.bots.platforms import _get_adapter
from app.services.integrations.bots.service import async_decrypt_credential
from app.utils.rate_limiter import rate_limiter
from app.utils.redis_util import async_get_redis_client
from app.utils.runtime_limits import runtime_slot

_seen_events: dict[str, float] = {}
_seen_lock = asyncio.Lock()


def _client_ip(request) -> str:
    """提取调用方 IP。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _mark_event_once(event_key: str) -> bool:
    """优先用 Redis 去重，故障时降级进程内去重。"""
    redis = await async_get_redis_client()
    if redis is not None:
        try:
            return bool(await redis.set(event_key, "1", nx=True, ex=600))
        except Exception:
            pass
    now = time.monotonic()
    async with _seen_lock:
        expired = [key for key, value in _seen_events.items() if value <= now]
        for key in expired[:1000]:
            _seen_events.pop(key, None)
        if event_key in _seen_events:
            return False
        if len(_seen_events) >= 20000:
            _seen_events.pop(next(iter(_seen_events)), None)
        _seen_events[event_key] = now + 600
        return True


async def _load_bot(bot_id: str) -> UserBot:
    """加载机器人并检查启用状态。"""
    async with AsyncSessionLocal() as session:
        bot = await session.get(UserBot, bot_id)
        if bot is None:
            raise ApiError("机器人不存在", code=404)
        if not bot.enabled:
            raise ApiError("机器人已停用", code=403)
        return bot


async def _owner_can_use_ai(owner_id: str) -> None:
    """校验机器人所属用户仍活跃且拥有 AI 权限。"""
    async with AsyncSessionLocal() as session:
        owner = await session.get(User, owner_id)
        if owner is None or not owner.is_active:
            raise ApiError("机器人所属账号不可用", code=403)
        permissions = await async_effective_permissions({"session": session, "user": owner})
        if owner.role != "super_admin" and "ai.use" not in permissions:
            raise ApiError("机器人所属账号没有 AI 使用权限", code=403)


async def _resolve_conversation(params: dict) -> str:
    """创建或复用平台聊天对应的 Agent 会话。"""
    async with AsyncSessionLocal() as session:
        mapping = (
            await session.execute(
                select(BotSessionMap).where(
                    BotSessionMap.bot_id == params["bot_id"],
                    BotSessionMap.conversation_key == params["conversation_key"],
                )
            )
        ).scalar_one_or_none()
        if mapping is not None:
            mapping.last_active_at = params["now"]
            await session.commit()
            return mapping.conversation_id
        conversation = AgentConversation(
            user_id=params["owner_id"],
            title=f"机器人 · {params['text'][:40]}",
            origin="bot",
        )
        session.add(conversation)
        await session.flush()
        session.add(
            BotSessionMap(
                bot_id=params["bot_id"],
                conversation_key=params["conversation_key"],
                conversation_id=conversation.id,
                last_active_at=params["now"],
            )
        )
        await session.commit()
        return conversation.id


async def async_handle_webhook(params: dict) -> dict:
    """验签、解析、映射会话并调用 Agent。参数：request / bot_id。"""
    request = params["request"]
    bot_id = params["bot_id"]
    raw_body = await request.body()
    if len(raw_body) > 64 * 1024:
        raise ApiError("Webhook 请求体不能超过 64KB")
    limit = await rate_limiter.check(f"rl:bot:{bot_id}:{_client_ip(request)}", 60, 60)
    if not limit["allowed"]:
        raise ApiError("机器人调用过于频繁，请稍后重试", code=429)

    bot = await _load_bot(bot_id)
    adapter = _get_adapter(bot.platform)
    secret = await async_decrypt_credential({"bot": bot})
    try:
        verified = adapter.verify(raw_body, request.headers, secret)
    except ValueError as exc:
        raise ApiError(str(exc), code=401) from exc
    try:
        event = adapter.parse(raw_body)
    except ValueError as exc:
        raise ApiError(str(exc), code=400) from exc
    if verified.event_id != event.event_id:
        raise ApiError("Webhook 事件 ID 不一致", code=401)
    event_key = f"bot:event:{bot_id}:{hashlib.sha256(event.event_id.encode()).hexdigest()}"
    if not await _mark_event_once(event_key):
        raise ApiError("该事件已处理", code=409)

    await _owner_can_use_ai(bot.user_id)
    conversation_key = hashlib.sha256(
        f"{bot_id}:{event.chat_type}:{event.chat_id}:{event.sender_id}".encode("utf-8")
    ).hexdigest()
    async with runtime_slot(
        "bot_invoke",
        "runtime.bot_max_concurrent_invocations",
        4,
        "机器人处理繁忙，请稍后重试",
    ):
        conversation_id = await _resolve_conversation(
            {
                "bot_id": bot.id,
                "owner_id": bot.user_id,
                "conversation_key": conversation_key,
                "text": event.text,
                "now": datetime.now(timezone.utc),
            }
        )
        try:
            reply = await asyncio.wait_for(
                async_run_turn(
                    {
                        "user_id": bot.user_id,
                        "conversation_id": conversation_id,
                        "content": event.text,
                        "tools_enabled": bot.tools_enabled,
                        "source": "bot",
                    }
                ),
                timeout=bot.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ApiError("机器人处理超时", code=504) from exc
    return adapter.render(str(reply or ""), conversation_id)
