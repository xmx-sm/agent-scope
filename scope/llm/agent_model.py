# -*- coding: utf-8 -*-
"""模型工厂对外入口。

业务侧只导入本文件，不直接依赖 ``agentscope.model`` / ``agentscope.credential``。
内部实现（注册表、参数过滤、构造器）在 :mod:`scope.llm._factory`。

统一返回信封::

    {"code": 200|400|500, "data": <模型对象>, "message": "..."}

四个入口:

    async_get_llm_model(data)          # data["llm"]
    async_get_embedding_model(data)    # data["embedding"]
    async_get_tts_model(data)          # data["tts"]
    async_get_asr_model(data)          # data["asr"]
    get_model_capabilities(provider)   # 前端/编排层能力描述

多模态说明
────────────────────────────────────────────────────────────────
模型工厂只负责“接线”：决定 ``input_types``、选择合适的 formatter、
把 ``DataBlock`` 送到模型 API。真正的图片/音频/视频内容由调用方构造::

    DataBlock(source=URLSource(url=..., media_type="video/mp4"))

视频必须显式 ``video_support=True``；支持 provider：
``openai-chat`` / ``openai-compatible`` / ``dashscope`` / ``gemini``。
文件解析（docx/xlsx/pptx 等）和落盘不属于模型工厂，分别属于 RAG/附件层
与上层的 media service。
"""

from __future__ import annotations

from typing import Any, Dict

from ._factory import (
    as_cfg,
    build_audio_model,
    build_chat_model,
    build_embedding_model,
    describe_capabilities,
    err,
    exception_response,
    normalize_provider,
    ok,
)


async def async_get_llm_model(data: dict = None) -> Dict[str, Any]:
    """构建 Chat 模型。

    入参（``data["llm"]``，也可直接平铺在 data）:
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

    返回:
        {"code":200, "data": ChatModel, "message":"模型初始化成功"}
        或 400/500 错误信封。
    """
    fn = "async_get_llm_model"
    provider = ""
    try:
        cfg = as_cfg(data, "llm")
        if not cfg:
            return err("缺少 llm 配置（provider/model 不能为空）", fn)
        provider = normalize_provider(cfg.get("provider"))
        return ok(build_chat_model(cfg), "模型初始化成功")
    except Exception as e:
        return exception_response(e, provider, fn)


async def async_get_embedding_model(data: dict = None) -> Dict[str, Any]:
    """构建 Embedding 模型（``data["embedding"]``）。

    入参:
        provider(str, 默认 openai)  openai / openai-chat / dashscope / gemini / ollama
        model(str, 必填)            向量模型 ID
        api_key / base_url
        dimensions(int, 默认 1536)
        context_size(int, 默认 8192)
        max_retries / retry_delay
        pass_dimensions(bool, 可选) 仅 OpenAI
        cache_dir(str, 可选)        本地 embedding 缓存目录
        cache_max_files / cache_max_size

    返回:
        {"code":200, "data": EmbeddingModel, "message":"Embedding 模型初始化成功"}
        或 400/500 错误信封。
    """
    fn = "async_get_embedding_model"
    provider = ""
    try:
        cfg = as_cfg(data, "embedding")
        provider = normalize_provider(cfg.get("provider", "openai"))
        return ok(build_embedding_model(cfg), "Embedding 模型初始化成功")
    except Exception as e:
        return exception_response(e, provider, fn)


async def async_get_tts_model(data: dict = None) -> Dict[str, Any]:
    """构建 TTS 模型（``data["tts"]``）。

    入参:
        provider(str, 默认 openai)  openai / dashscope / gemini / minimax
        mode(str, 默认 standard)    dashscope 支持 standard/cosyvoice/realtime
        model(str, 可选)            不传则用各模型默认
        api_key / base_url
        stream(bool, 默认 True)
        parameters(dict)            模型参数，如 {"voice": "..."}
        cold_start_length / cold_start_words（cosyvoice/realtime）

    说明:
        TTS 模型只生成音频数据（TTSResponse.content 为 DataBlock），
        **不接收输出路径，也不写文件**；落盘由调用方或 media service 负责。
    """
    fn = "async_get_tts_model"
    provider = ""
    try:
        cfg = as_cfg(data, "tts")
        provider = normalize_provider(cfg.get("provider", "openai"))
        return ok(build_audio_model(cfg, "tts"), "tts 模型初始化成功")
    except Exception as e:
        return exception_response(e, provider, fn)


async def async_get_asr_model(data: dict = None) -> Dict[str, Any]:
    """构建 ASR 模型（``data["asr"]``）。

    入参:
        provider(str, 默认 openai)  openai / dashscope
        mode(str, 默认 standard)    dashscope 支持 standard/realtime
        model(str, 可选)
        api_key / base_url
        parameters(dict)            模型参数（language、vocabulary 等）

    说明:
        ASR 返回文本（ASRResponse.content 为 TextBlock），不产生输出文件。
    """
    fn = "async_get_asr_model"
    provider = ""
    try:
        cfg = as_cfg(data, "asr")
        provider = normalize_provider(cfg.get("provider", "openai"))
        return ok(build_audio_model(cfg, "asr"), "asr 模型初始化成功")
    except Exception as e:
        return exception_response(e, provider, fn)


def get_model_capabilities(provider: Any) -> Dict[str, Any]:
    """返回某 provider 的能力描述（静态近似，最终以具体模型卡为准）。

    返回 data:
        {
          "provider": str,
          "chat": bool,
          "embedding": bool,
          "tts": bool,
          "asr": bool,
          "input_types": list[str],
          "video_support": bool,
        }
    """
    try:
        return ok(describe_capabilities(provider))
    except Exception as e:
        return err(str(e), "get_model_capabilities")


__all__ = [
    "async_get_llm_model",
    "async_get_embedding_model",
    "async_get_tts_model",
    "async_get_asr_model",
    "get_model_capabilities",
]
