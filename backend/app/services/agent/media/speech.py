"""AI 回复语音合成（复用 scope TTS 工厂）。"""

from __future__ import annotations

import base64

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.services.config.service import async_get_config
from app.utils.runtime_limits import runtime_slot


async def async_config(params: dict) -> dict:
    """读取 TTS 系统配置。参数：session。"""
    session: AsyncSession = params["session"]

    async def get(key: str, default=""):
        """读取系统配置。"""
        return await async_get_config({"session": session, "key": key, "default": default})

    return {
        "enabled": bool(await get("ai.tts.enabled", False)),
        "provider": str(await get("ai.tts.provider", "dashscope") or "dashscope"),
        "model": str(await get("ai.tts.model", "qwen3-tts-flash") or ""),
        "base_url": str(await get("ai.tts.base_url", "") or ""),
        "api_key": str(await get("ai.tts.api_key", "") or ""),
        "voice": str(await get("ai.tts.voice", "Cherry") or "Cherry"),
    }


async def async_synthesize(params: dict) -> dict:
    """把文本合成为音频，并应用动态出站并发限制。

        参数：text / voice / model / session。
        """
    async with runtime_slot(
        "external_call",
        "runtime.external_call_max_concurrency",
        16,
        "语音服务繁忙，请稍后重试",
    ):
        return await _async_synthesize(params)


async def _async_synthesize(params: dict) -> dict:
    """执行文本转语音。"""
    session: AsyncSession = params["session"]
    text = str(params.get("text") or "").strip()
    if not text:
        raise ApiError("朗读文本不能为空")
    if len(text) > 2000:
        raise ApiError("单次朗读最多 2000 字")
    cfg = await async_config({"session": session})
    if not cfg["enabled"]:
        raise ApiError("语音合成未启用，请到默认配置 → Agent 配置 → 语音合成开启")
    if not cfg["model"] or not cfg["api_key"]:
        raise ApiError("请先配置 TTS 模型与 API Key")
    tts = {
        "provider": cfg["provider"],
        "model": cfg["model"],
        "api_key": cfg["api_key"],
        "stream": True,
        "parameters": {"voice": str(params.get("voice") or cfg["voice"])},
    }
    if cfg["base_url"]:
        tts["base_url"] = cfg["base_url"]
    if params.get("model"):
        tts["model"] = str(params["model"])
    from scope.media.tts import async_generate_tts

    result = await async_generate_tts(
        {"tts": tts, "text": text, "output_mode": "base64"}
    )
    if result.get("code") != 200:
        raise ApiError(result.get("message") or "语音合成失败")
    data = result["data"]
    return {
        "audio": base64.b64decode(data["base64"]),
        "media_type": data.get("media_type") or "audio/mpeg",
        "bytes": data.get("bytes") or 0,
    }
