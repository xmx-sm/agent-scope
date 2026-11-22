# -*- coding: utf-8 -*-
"""模型工厂：配置字典 → AgentScope 模型 / 凭证实例。

设计原则
────────────────────────────────────────────────────────────────
1. **只做映射，不重写 SDK**：provider → 模型类 / 凭证类 / formatter 类，
   其余参数原样交给 AgentScope。
2. **按目标类签名过滤**：不同版本、不同厂商的参数集合不同，构造前用
   ``inspect.signature`` / ``Parameters.model_fields`` 过滤，避免把
   ``client_kwargs`` 传给不支持的类。
3. **多模态在工厂里只解决“接线”**：
   - 文本/图片/音频/PDF 由各厂商默认 formatter 处理；
   - 视频需要显式 ``video_support=True``，工厂换用视频增强 formatter
     （openai-chat / openai-compatible / dashscope / gemini）；
   - DataBlock 的构造、附件读取、大小限制属于消息/附件层，不在本文件做。
4. **敏感信息不落代码**：api_key / base_url 由调用方或 config 层注入。

统一入口
────────────────────────────────────────────────────────────────
    async_get_llm_model(data)          # data["llm"]
    async_get_embedding_model(data)    # data["embedding"]
    async_get_tts_model(data)          # data["tts"]
    async_get_asr_model(data)          # data["asr"]
    get_model_capabilities(provider)   # 给前端/编排层的能力描述

返回统一信封 ``{"code": 200|400|500, "data": ..., "message": ...}``。
"""

from __future__ import annotations

import importlib
import inspect
import os
from typing import Any, Dict, Optional

from .formatters import DashScopeVideoChatFormatter, OpenAIVideoChatFormatter


# ── provider 归一化 ──────────────────────────────────────────────
_PROVIDER_ALIASES = {
    "openai": "openai",
    "openai-response": "openai",
    "openai-responses": "openai",
    "openai-chat": "openai-chat",
    "openai-compatible": "openai-chat",
    "openai_compatible": "openai-chat",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "dashscope": "dashscope",
    "qwen": "dashscope",
    "deepseek": "deepseek",
    "gemini": "gemini",
    "google": "gemini",
    "moonshot": "moonshot",
    "kimi": "moonshot",
    "xai": "xai",
    "grok": "xai",
    "ollama": "ollama",
    "minimax": "minimax",
    "volcengine": "volcengine",
    "doubao": "volcengine",
}

# provider -> (模块, 类名)
_CHAT_REGISTRY = {
    "openai": ("agentscope.model", "OpenAIResponseModel"),
    "openai-chat": ("agentscope.model", "OpenAIChatModel"),
    "anthropic": ("agentscope.model", "AnthropicChatModel"),
    "dashscope": ("agentscope.model", "DashScopeChatModel"),
    "deepseek": ("agentscope.model", "DeepSeekChatModel"),
    "gemini": ("agentscope.model", "GeminiChatModel"),
    "minimax": ("agentscope.model", "MiniMaxChatModel"),
    "moonshot": ("agentscope.model", "MoonshotChatModel"),
    "xai": ("agentscope.model", "XAIChatModel"),
    "ollama": ("agentscope.model", "OllamaChatModel"),
    "volcengine": ("agentscope.model", "VolcengineChatModel"),
}

_CREDENTIAL_REGISTRY = {
    "openai": ("agentscope.credential", "OpenAICredential"),
    "openai-chat": ("agentscope.credential", "OpenAICredential"),
    "anthropic": ("agentscope.credential", "AnthropicCredential"),
    "dashscope": ("agentscope.credential", "DashScopeCredential"),
    "deepseek": ("agentscope.credential", "DeepSeekCredential"),
    "gemini": ("agentscope.credential", "GeminiCredential"),
    "minimax": ("agentscope.credential", "MiniMaxCredential"),
    "moonshot": ("agentscope.credential", "MoonshotCredential"),
    "xai": ("agentscope.credential", "XAICredential"),
    "ollama": ("agentscope.credential", "OllamaCredential"),
    "volcengine": ("agentscope.credential", "VolcengineCredential"),
}

_FORMATTER_REGISTRY = {
    "openai": ("agentscope.formatter", "OpenAIResponseFormatter"),
    "openai-chat": ("agentscope.formatter", "OpenAIChatFormatter"),
    "anthropic": ("agentscope.formatter", "AnthropicChatFormatter"),
    "dashscope": ("agentscope.formatter", "DashScopeChatFormatter"),
    "deepseek": ("agentscope.formatter", "DeepSeekChatFormatter"),
    "gemini": ("agentscope.formatter", "GeminiChatFormatter"),
    "minimax": ("agentscope.formatter", "MiniMaxChatFormatter"),
    "moonshot": ("agentscope.formatter", "MoonshotChatFormatter"),
    "xai": ("agentscope.formatter", "XAIChatFormatter"),
    "ollama": ("agentscope.formatter", "OllamaChatFormatter"),
    "volcengine": ("agentscope.formatter", "VolcengineChatFormatter"),
}

_EMBEDDING_REGISTRY = {
    "openai": ("agentscope.embedding", "OpenAIEmbeddingModel", "openai"),
    "openai-chat": ("agentscope.embedding", "OpenAIEmbeddingModel", "openai"),
    "dashscope": ("agentscope.embedding", "DashScopeEmbeddingModel", "dashscope"),
    "gemini": ("agentscope.embedding", "GeminiEmbeddingModel", "gemini"),
    "ollama": ("agentscope.embedding", "OllamaEmbeddingModel", "ollama"),
}

# (provider, mode) -> (模块, 类名, 凭证 provider)
_TTS_REGISTRY = {
    ("openai", "standard"): ("agentscope.tts", "OpenAITTSModel", "openai"),
    ("dashscope", "standard"): ("agentscope.tts", "DashScopeTTSModel", "dashscope"),
    ("dashscope", "cosyvoice"): ("agentscope.tts", "DashScopeCosyVoiceTTSModel", "dashscope"),
    ("dashscope", "realtime"): ("agentscope.tts", "DashScopeRealtimeTTSModel", "dashscope"),
    ("gemini", "standard"): ("agentscope.tts", "GeminiTTSModel", "gemini"),
    ("minimax", "standard"): ("agentscope.tts", "MiniMaxTTSModel", "minimax"),
}

_ASR_REGISTRY = {
    ("openai", "standard"): ("agentscope.asr", "OpenAIASRModel", "openai"),
    ("dashscope", "standard"): ("agentscope.asr", "DashScopeASRModel", "dashscope"),
    ("dashscope", "realtime"): ("agentscope.asr", "DashScopeRealtimeASRModel", "dashscope"),
}

# 能力描述：仅用于前端/编排层展示，最终以各厂商模型卡为准。
_INPUT_TYPES = {
    "openai": ["text/plain", "image/*", "application/pdf"],
    "openai-chat": ["text/plain", "image/*", "audio/*", "application/pdf"],
    "anthropic": ["text/plain", "image/*", "application/pdf"],
    "dashscope": ["text/plain", "image/*", "audio/*", "video/*"],
    "deepseek": ["text/plain"],
    "gemini": ["text/plain", "image/*", "audio/*", "video/*", "application/pdf"],
    "minimax": ["text/plain", "audio/*"],
    "moonshot": ["text/plain"],
    "xai": ["text/plain"],
    "ollama": ["text/plain", "image/*"],
    "volcengine": ["text/plain"],
}

_VIDEO_PROVIDERS = {"openai-chat", "dashscope", "gemini"}

# 可选 SDK：构造模型/调用时才 import，缺失时给明确安装指引
_DEPENDENCY_HINTS = {
    "anthropic": "anthropic",
    "dashscope": "dashscope",
    "gemini": "google-genai",
    "minimax": "openai",
    "moonshot": "openai",
    "ollama": "ollama",
    "volcengine": "volcengine-python-sdk",
    "xai": "openai",
}


def _exception_response(exc: BaseException, provider: str, fn: str) -> Dict[str, Any]:
    """把构造期异常统一成信封；可选依赖缺失给 pip 指引。"""
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        pkg = _DEPENDENCY_HINTS.get(provider)
        if pkg:
            return _err(f"未安装或缺少依赖 {pkg}（pip install {pkg}）", fn)
    if isinstance(exc, (TypeError, ValueError, RuntimeError)):
        return _err(str(exc), fn)
    return _err(f"模型初始化失败：{type(exc).__name__}: {exc}", fn, code=500)



def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, fn: str = "", code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _load(module: str, name: str) -> Any:
    try:
        mod = importlib.import_module(module)
    except ImportError as e:
        raise RuntimeError(f"缺少依赖或模块 {module}：{e}") from e
    try:
        return getattr(mod, name)
    except AttributeError as e:
        raise RuntimeError(f"{module} 中不存在 {name}，可能是 agentscope 版本不匹配") from e


def _normalize_provider(provider: Any) -> str:
    key = str(provider or "").strip().lower()
    if key not in _PROVIDER_ALIASES:
        raise ValueError(
            f"不支持的 provider: {provider!r}，支持: "
            + ", ".join(sorted(set(_PROVIDER_ALIASES.values())))
        )
    return _PROVIDER_ALIASES[key]


def _as_cfg(data: Optional[dict], section: str) -> dict:
    """取 data[section]；兼容直接把配置平铺在 data 顶层的写法。"""
    if not data:
        return {}
    if not isinstance(data, dict):
        raise TypeError("data 必须是字典对象")
    cfg = data.get(section)
    if isinstance(cfg, dict):
        return cfg
    if cfg is None and any(k in data for k in ("provider", "model", "api_key", "base_url")):
        return data
    return {}


def _filter_init_kwargs(cls: Any, kwargs: dict) -> dict:
    """按目标类 __init__ 签名过滤；带 **kwargs 的类原样返回。"""
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    allowed = set(params) - {"self"}
    return {k: v for k, v in kwargs.items() if k in allowed and v is not None}


def _build_credential(provider: str, cfg: dict) -> Any:
    module, name = _CREDENTIAL_REGISTRY[provider]
    cls = _load(module, name)
    fields = set(getattr(cls, "model_fields", {}) or {})

    kwargs: dict[str, Any] = {}
    explicit = cfg.get("credential") or cfg.get("credential_kwargs") or {}
    if isinstance(explicit, dict):
        kwargs.update({k: v for k, v in explicit.items() if k in fields and v is not None})

    for key in ("api_key", "organization", "websocket_url"):
        if cfg.get(key) is not None and key in fields:
            kwargs.setdefault(key, cfg[key])

    base_url = cfg.get("base_url")
    if base_url:
        # 不同 provider 的字段名不同：OpenAI base_url / Ollama host / xAI api_host
        for field in ("base_url", "host", "api_host"):
            if field in fields:
                kwargs.setdefault(field, base_url)
                break

    try:
        return cls(**kwargs)
    except Exception as e:
        raise ValueError(f"凭证构造失败（provider={provider}）：{e}") from e


def _build_parameters(model_cls: Any, provider: str, cfg: dict) -> Any:
    params_cls = getattr(model_cls, "Parameters", None)
    if params_cls is None:
        return None
    fields = set(getattr(params_cls, "model_fields", {}) or {})
    if not fields:
        return None

    think = bool(cfg.get("think", False))
    values: dict[str, Any] = {}

    if think and provider != "openai-chat" and "thinking_enable" in fields:
        values["thinking_enable"] = True
    if think and "thinking_budget" in fields and cfg.get("thinking_budget") is not None:
        values["thinking_budget"] = cfg["thinking_budget"]
    for key in ("reasoning_effort", "max_tokens", "temperature", "top_p", "top_k", "voice"):
        if cfg.get(key) is not None and key in fields:
            values[key] = cfg[key]
    if cfg.get("tool", True) and "parallel_tool_calls" in fields:
        values["parallel_tool_calls"] = True

    explicit = cfg.get("parameters")
    if isinstance(explicit, dict):
        values.update({k: v for k, v in explicit.items() if k in fields})

    if not values:
        return None
    try:
        return params_cls(**values)
    except Exception as e:
        raise ValueError(f"模型参数构造失败：{e}") from e


def _build_formatter(provider: str, cfg: dict) -> Any:
    video_support = bool(cfg.get("video_support", False))
    raw_input_types = cfg.get("input_types")
    input_types: Optional[list[str]] = None
    if raw_input_types is not None:
        if not isinstance(raw_input_types, list) or not all(isinstance(x, str) for x in raw_input_types):
            raise ValueError("input_types 必须是字符串列表")
        input_types = list(raw_input_types)

    video_fps = cfg.get("video_fps")
    if video_fps is not None:
        try:
            video_fps = float(video_fps)
        except (TypeError, ValueError) as e:
            raise ValueError("video_fps 必须是数字") from e

    if video_fps is not None and not video_support:
        raise ValueError("配置了 video_fps 但未开启 video_support")
    if input_types is not None and any(t.startswith("video/") for t in input_types) \
            and not video_support:
        raise ValueError("input_types 含 video/* 时必须设置 video_support=True")

    if video_support:
        if provider not in _VIDEO_PROVIDERS:
            raise ValueError(
                f"provider={provider} 不支持 video_support；"
                f"可选: {', '.join(sorted(_VIDEO_PROVIDERS))}"
            )
        types = list(input_types or _INPUT_TYPES[provider])
        if not any(t.startswith("video/") for t in types):
            types.append("video/*")
        if provider == "openai-chat":
            return OpenAIVideoChatFormatter(input_types=types, video_fps=video_fps)
        if provider == "dashscope":
            return DashScopeVideoChatFormatter(input_types=types, video_fps=video_fps)
        # Gemini 默认 formatter 已支持 video/*，只有显式改 input_types 时才需要构造
        if input_types is not None:
            module, name = _FORMATTER_REGISTRY[provider]
            return _load(module, name)(input_types=types)
        return None

    if input_types is not None:
        module, name = _FORMATTER_REGISTRY[provider]
        return _load(module, name)(input_types=input_types)
    return None


def get_model_capabilities(provider: Any) -> Dict[str, Any]:
    """返回某 provider 的能力描述（静态近似，最终以具体模型卡为准）。"""
    try:
        key = _normalize_provider(provider)
    except ValueError as e:
        return _err(str(e), "get_model_capabilities")
    return _ok({
        "provider": key,
        "chat": key in _CHAT_REGISTRY,
        "embedding": key in _EMBEDDING_REGISTRY,
        "tts": any(p == key for p, _ in _TTS_REGISTRY),
        "asr": any(p == key for p, _ in _ASR_REGISTRY),
        "input_types": list(_INPUT_TYPES.get(key, ["text/plain"])),
        "video_support": key in _VIDEO_PROVIDERS,
    })


def _build_chat_model(cfg: dict) -> Any:
    if not cfg.get("provider"):
        raise ValueError("缺少 provider")
    provider = _normalize_provider(cfg.get("provider"))
    model = cfg.get("model")
    if not model:
        raise ValueError("缺少 model（模型 ID）")

    module, name = _CHAT_REGISTRY[provider]
    model_cls = _load(module, name)
    credential = _build_credential(provider, cfg)

    kwargs: dict[str, Any] = {
        "credential": credential,
        "model": model,
        "stream": cfg.get("stream", True),
        "max_retries": cfg.get("max_retries", 3),
        "retry_delay": cfg.get("retry_delay", 1.0),
    }
    for key in ("context_size", "raise_on_refusal", "raise_on_content_filter"):
        if cfg.get(key) is not None:
            kwargs[key] = cfg[key]

    client_kwargs = dict(cfg.get("client_kwargs") or {})
    if provider == "openai-chat":
        # 默认 180s，避免服务端长时间无响应导致流式永久挂起
        client_kwargs.setdefault("timeout", 180)
    if client_kwargs:
        kwargs["client_kwargs"] = client_kwargs

    # openai 兼容端点的思考参数走 extra_body，不映射到 Parameters.thinking_enable
    if bool(cfg.get("think", False)) and provider == "openai-chat":
        extra = dict(cfg.get("thinking_params") or cfg.get("extra_body") or {})
        if not cfg.get("thinking_params"):
            extra.setdefault("enable_thinking", True)
        if cfg.get("thinking_budget") is not None:
            extra.setdefault("thinking_budget", cfg["thinking_budget"])
        kwargs["extra_body"] = extra
    elif cfg.get("extra_body") is not None:
        kwargs["extra_body"] = cfg["extra_body"]

    formatter = _build_formatter(provider, cfg)
    if formatter is not None:
        kwargs["formatter"] = formatter

    parameters = _build_parameters(model_cls, provider, cfg)
    if parameters is not None:
        kwargs["parameters"] = parameters

    return model_cls(**_filter_init_kwargs(model_cls, kwargs))


async def async_get_llm_model(data: dict = None) -> Dict[str, Any]:
    """构建 Chat 模型。

    入参（data["llm"]，也可直接平铺在 data）:
        provider(str, 必填)      openai / openai-chat / openai-compatible /
                                 anthropic / dashscope / deepseek / gemini /
                                 moonshot / xai / ollama / minimax / volcengine
        model(str, 必填)         模型 ID
        api_key(str, 可选)       Ollama 可不填
        base_url(str, 可选)      按 provider 映射到 base_url / host / api_host
        organization(str, 可选)  仅 OpenAI
        stream(bool, 默认 True)
        context_size(int, 可选)  不传则用 AgentScope 默认
        max_retries / retry_delay
        think(bool, 默认 False) / thinking_budget(int) / reasoning_effort(str)
        max_tokens / temperature / top_p / top_k / voice
        tool(bool, 默认 True)    是否启用工具调用
        thinking_params(dict)    openai-chat 的思考参数（默认 enable_thinking）
        extra_body(dict)         透传给请求体
        client_kwargs(dict)      SDK 客户端参数
        parameters(dict)         显式覆盖模型 Parameters
        input_types(list[str])   多模态能力，如 ["text/plain","image/*"]
        video_support(bool)      是否发送 video/* 数据块
        video_fps(float, 可选)   视频抽帧率（仅部分 provider 支持）

    多模态说明:
        input_types 只决定 formatter 放行哪些 DataBlock；真正的图片/音频/视频
        内容由调用方构造 DataBlock 并放进 Msg。视频必须显式
        video_support=True，否则默认 formatter 会跳过 video/*。
    """
    fn = "async_get_llm_model"
    provider = ""
    try:
        cfg = _as_cfg(data, "llm")
        if not cfg:
            return _err("缺少 llm 配置（provider/model 不能为空）", fn)
        provider = _normalize_provider(cfg.get("provider"))
        model = _build_chat_model(cfg)
        return _ok(model, "模型初始化成功")
    except Exception as e:
        return _exception_response(e, provider, fn)


async def async_get_embedding_model(data: dict = None) -> Dict[str, Any]:
    """构建 Embedding 模型（data["embedding"]）。"""
    fn = "async_get_embedding_model"
    provider = ""
    try:
        cfg = _as_cfg(data, "embedding")
        provider = _normalize_provider(cfg.get("provider", "openai"))
        if provider not in _EMBEDDING_REGISTRY:
            return _err(f"provider={provider} 不支持 embedding", fn)
        model = cfg.get("model")
        if not model:
            return _err("缺少 embedding.model", fn)

        module, name, cred_provider = _EMBEDDING_REGISTRY[provider]
        cls = _load(module, name)
        credential = _build_credential(cred_provider, cfg)
        kwargs: dict[str, Any] = {
            "credential": credential,
            "model": model,
            "dimensions": cfg.get("dimensions", 1536),
            "context_size": cfg.get("context_size", 8192),
            "max_retries": cfg.get("max_retries", 3),
            "retry_delay": cfg.get("retry_delay", 1.0),
        }
        for key in ("pass_dimensions",):
            if cfg.get(key) is not None:
                kwargs[key] = cfg[key]

        cache_dir = cfg.get("cache_dir")
        if cache_dir:
            from agentscope.embedding import FileEmbeddingCache
            kwargs["embedding_cache"] = FileEmbeddingCache(
                cache_dir=cache_dir,
                max_file_number=cfg.get("cache_max_files"),
                max_cache_size=cfg.get("cache_max_size"),
            )

        return _ok(cls(**_filter_init_kwargs(cls, kwargs)), "Embedding 模型初始化成功")
    except Exception as e:
        return _exception_response(e, provider, fn)


def _build_audio_model(data: Optional[dict], section: str, registry: dict,
                       fn: str) -> Dict[str, Any]:
    provider = ""
    try:
        cfg = _as_cfg(data, section)
        provider = _normalize_provider(cfg.get("provider", "openai"))
        mode = str(cfg.get("mode") or "standard").strip().lower()
        key = (provider, mode)
        if key not in registry:
            modes = ", ".join(sorted(m for p, m in registry if p == provider)) or "无"
            if provider not in {p for p, _ in registry}:
                return _err(f"provider={provider} 不支持 {section}", fn)
            return _err(f"provider={provider} 不支持 mode={mode}（可选: {modes}）", fn)

        module, name, cred_provider = registry[key]
        cls = _load(module, name)
        credential = _build_credential(cred_provider, cfg)
        kwargs: dict[str, Any] = {"credential": credential}
        if cfg.get("model"):
            kwargs["model"] = cfg["model"]
        for k in ("stream", "max_retries", "retry_delay", "client_kwargs",
                  "cold_start_length", "cold_start_words"):
            if cfg.get(k) is not None:
                kwargs[k] = cfg[k]

        params_cls = getattr(cls, "Parameters", None)
        explicit = cfg.get("parameters")
        if params_cls is not None and isinstance(explicit, dict):
            fields = set(getattr(params_cls, "model_fields", {}) or {})
            values = {k: v for k, v in explicit.items() if k in fields}
            if values:
                kwargs["parameters"] = params_cls(**values)

        return _ok(cls(**_filter_init_kwargs(cls, kwargs)), f"{section} 模型初始化成功")
    except Exception as e:
        return _exception_response(e, provider, fn)


async def async_get_tts_model(data: dict = None) -> Dict[str, Any]:
    """构建 TTS 模型（data["tts"]；mode=standard/cosyvoice/realtime）。"""
    return _build_audio_model(data, "tts", _TTS_REGISTRY, "async_get_tts_model")


async def async_get_asr_model(data: dict = None) -> Dict[str, Any]:
    """构建 ASR 模型（data["asr"]；mode=standard/realtime）。"""
    return _build_audio_model(data, "asr", _ASR_REGISTRY, "async_get_asr_model")


__all__ = [
    "async_get_llm_model",
    "async_get_embedding_model",
    "async_get_tts_model",
    "async_get_asr_model",
    "get_model_capabilities",
]
