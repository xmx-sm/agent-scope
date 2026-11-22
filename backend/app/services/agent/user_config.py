"""用户级 Agent 配置：系统默认 + 个人覆盖。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import User, UserAgentConfig
from app.services.config.service import async_get_config
from app.utils.mask import SENTINEL, mask_secret

FIELDS = (
    "provider",
    "base_url",
    "api_key",
    "model",
    "temperature",
    "max_tokens",
    "context_window",
    "stream",
    "think",
    "thinking_budget",
    "reasoning_effort",
    "system_prompt",
)


async def async_system_defaults(session: AsyncSession) -> dict[str, Any]:
    async def get(key: str, default: Any = ""):
        return await async_get_config({"session": session, "key": key, "default": default})

    return {
        "provider": await get("ai.provider", "openai-compatible"),
        "base_url": await get("ai.base_url", ""),
        "api_key": await get("ai.api_key", ""),
        "model": await get("ai.model", ""),
        "temperature": await get("ai.temperature", 0.7),
        "max_tokens": await get("ai.max_tokens", 4096),
        "context_window": await get("ai.context_window", 131072),
        "stream": await get("ai.stream", True),
        "think": await get("ai.think", False),
        "thinking_budget": await get("ai.thinking_budget", 0),
        "reasoning_effort": await get("ai.reasoning_effort", "medium"),
        "system_prompt": await get("ai.system_prompt", ""),
    }


async def async_effective(params: dict) -> dict[str, Any]:
    """参数：session / user"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    system = await async_system_defaults(session)
    row = await session.get(UserAgentConfig, user.id)
    if row is None or row.use_system_default:
        return {**system, "source": "system"}
    return {
        "provider": row.provider or system["provider"],
        "base_url": row.base_url,
        "api_key": row.api_key,
        "model": row.model,
        "temperature": row.temperature,
        "max_tokens": row.max_tokens,
        "context_window": row.context_window,
        "stream": row.stream,
        "think": row.think,
        "thinking_budget": row.thinking_budget,
        "reasoning_effort": row.reasoning_effort,
        "system_prompt": row.system_prompt or system["system_prompt"],
        "source": "user",
    }


async def async_view(params: dict) -> dict[str, Any]:
    """参数：session / user"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    system = await async_system_defaults(session)
    effective = await async_effective({"session": session, "user": user})
    row = await session.get(UserAgentConfig, user.id)
    raw = {
        "provider": row.provider if row else "",
        "base_url": row.base_url if row else "",
        "api_key": row.api_key if row else "",
        "model": row.model if row else "",
        "temperature": row.temperature if row else system["temperature"],
        "max_tokens": row.max_tokens if row else system["max_tokens"],
        "context_window": row.context_window if row else system["context_window"],
        "stream": row.stream if row else system["stream"],
        "think": row.think if row else system["think"],
        "thinking_budget": row.thinking_budget if row else system["thinking_budget"],
        "reasoning_effort": row.reasoning_effort if row else system["reasoning_effort"],
        "system_prompt": row.system_prompt if row else "",
    }
    return {
        "source": effective["source"],
        "use_system_default": row.use_system_default if row else True,
        "effective": {**effective, "api_key": mask_secret(effective["api_key"]),
                      "system_prompt": effective["system_prompt"]},
        "user": {**raw, "api_key": mask_secret(raw["api_key"])},
        "system": {**system, "api_key": mask_secret(system["api_key"]),
                   "system_prompt": system["system_prompt"]},
    }


async def async_save(params: dict) -> dict[str, Any]:
    """参数：session / user / data"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    data: dict = params["data"]
    row = await session.get(UserAgentConfig, user.id)
    if row is None:
        row = UserAgentConfig(user_id=user.id)
        session.add(row)

    use_default = bool(data.get("use_system_default", False))
    row.use_system_default = use_default
    if not use_default:
        api_key = str(data.get("api_key") or "")
        if api_key == SENTINEL:
            api_key = row.api_key
        if not str(data.get("model") or "").strip():
            raise ApiError("自定义模式必须填写模型")
        if not str(data.get("base_url") or "").strip():
            raise ApiError("自定义模式必须填写 API 地址")
        row.provider = str(data.get("provider") or "openai-compatible")
        row.base_url = str(data.get("base_url") or "").strip()
        row.api_key = api_key
        row.model = str(data.get("model") or "").strip()
        row.temperature = float(data.get("temperature", 0.7) or 0.7)
        row.max_tokens = int(data.get("max_tokens", 4096) or 4096)
        row.context_window = int(data.get("context_window", 131072) or 131072)
        row.stream = bool(data.get("stream", True))
        row.think = bool(data.get("think", False))
        row.thinking_budget = int(data.get("thinking_budget", 0) or 0)
        row.reasoning_effort = str(data.get("reasoning_effort") or "medium")
        row.system_prompt = str(data.get("system_prompt") or "")
    await session.commit()
    return await async_view({"session": session, "user": user})


async def async_reset(params: dict) -> dict[str, Any]:
    """参数：session / user"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    row = await session.get(UserAgentConfig, user.id)
    if row is not None:
        row.use_system_default = True
        await session.commit()
    return await async_view({"session": session, "user": user})
