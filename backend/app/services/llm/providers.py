"""Agent 模型配置辅助：厂商预设与模型列表拉取。"""

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.services.config.service import async_get_config
from app.utils.mask import SENTINEL

PROVIDERS: list[dict[str, Any]] = [
    {"value": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1"},
    {"value": "openai-compatible", "label": "OpenAI 兼容（自定义）", "base_url": ""},
    {"value": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com/v1"},
    {"value": "dashscope", "label": "阿里云百炼 / DashScope",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    {"value": "moonshot", "label": "Moonshot", "base_url": "https://api.moonshot.cn/v1"},
    {"value": "zhipu", "label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4"},
    {"value": "ollama", "label": "Ollama", "base_url": "http://127.0.0.1:11434/v1"},
    {"value": "vllm", "label": "vLLM", "base_url": "http://127.0.0.1:8000/v1"},
    {"value": "lmstudio", "label": "LM Studio", "base_url": "http://127.0.0.1:1234/v1"},
    {"value": "custom", "label": "自定义", "base_url": ""},
]

_PROVIDER_MAP = {item["value"]: item for item in PROVIDERS}


async def async_list_providers(params: dict) -> list[dict[str, Any]]:
    """列出模型厂商预设

    参数：无（保留字典签名统一）
    """
    return PROVIDERS


async def async_fetch_models(params: dict) -> dict[str, Any]:
    """拉取厂商模型列表

    参数：provider / base_url / api_key
    """
    provider = str(params.get("provider") or "").strip()
    base_url = str(params.get("base_url") or "").strip()
    api_key = str(params.get("api_key") or "").strip()
    key_config = str(params.get("key_config") or "").strip()
    session: AsyncSession | None = params.get("session")

    if (not api_key or api_key == SENTINEL) and key_config and session is not None:
        api_key = str(
            await async_get_config(
                {"session": session, "key": key_config, "default": ""}
            )
            or ""
        ).strip()

    if not base_url:
        base_url = str((_PROVIDER_MAP.get(provider) or {}).get("base_url") or "")
    if not base_url:
        raise ApiError("请先填写模型厂商的 API 地址")
    if not base_url.startswith(("http://", "https://")):
        raise ApiError("API 地址必须以 http:// 或 https:// 开头")

    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        raise ApiError("获取模型列表超时，请检查 API 地址与网络")
    except httpx.HTTPError as exc:
        raise ApiError(f"获取模型列表失败：{exc}")

    if response.status_code >= 400:
        detail = response.text[:200].replace("\n", " ")
        raise ApiError(f"模型厂商返回 HTTP {response.status_code}：{detail}")

    try:
        payload = response.json()
    except ValueError:
        raise ApiError("模型厂商返回的不是 JSON，请检查 API 地址")

    raw_items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raw_items = (payload.get("models") if isinstance(payload, dict) else None) or []
    models = []
    for item in raw_items:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or item.get("model")
        else:
            model_id = None
        if model_id:
            models.append(str(model_id))
    if not models:
        raise ApiError("未获取到模型列表，请确认厂商是否支持 /models 接口")
    return {"base_url": base_url, "models": sorted(set(models))}
