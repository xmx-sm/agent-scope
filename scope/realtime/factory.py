# -*- coding: utf-8 -*-
"""实时语音（Speech-to-Speech）字典工厂。

官方组件：

- ``RealtimeModelBase``：DashScope / OpenAI / Gemini / xAI 实时模型
- ``RealtimeAgent``：维护语音回合、打断、工具调用与 HITL
- ``LocalAudioTransport``：本地麦克风与扬声器

本层只负责字典构建，不复制官方实时会话、VAD 或音频逻辑。
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Dict, List, Optional

from agentscope.agent import RealtimeAgent, TurnAggregator
from agentscope.state import AgentState
from agentscope.realtime import (
    DashScopeAudioRealtimeModel,
    DashScopeRealtimeModel,
    GeminiRealtimeModel,
    LocalAudioTransport,
    OpenAILiveModel,
    OpenAIRealtimeModel,
    RealtimeModelBase,
    TransportBase,
    XAIRealtimeModel,
)
from agentscope.tool import Toolkit

try:
    from ..llm._factory import _build_credential
except ImportError:
    from llm._factory import _build_credential

try:
    from ..permission.bundle import async_build_permission_bundle
except ImportError:
    from permission.bundle import async_build_permission_bundle

try:
    from ..agent.subagents import build_subagent_toolkit
except ImportError:
    from agent.subagents import build_subagent_toolkit

_MODEL_TYPES = {
    "dashscope": DashScopeRealtimeModel,
    "dashscope_omni": DashScopeRealtimeModel,
    "dashscope_qwen_omni": DashScopeRealtimeModel,
    "dashscope_audio": DashScopeAudioRealtimeModel,
    "dashscope_qwen_audio": DashScopeAudioRealtimeModel,
    "openai": OpenAIRealtimeModel,
    "openai_realtime": OpenAIRealtimeModel,
    "openai_live": OpenAILiveModel,
    "openai_gpt_live": OpenAILiveModel,
    "gemini": GeminiRealtimeModel,
    "gemini_live": GeminiRealtimeModel,
    "xai": XAIRealtimeModel,
    "xai_realtime": XAIRealtimeModel,
    "grok": XAIRealtimeModel,
}


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "y")
    return bool(value)


def _merge_agent_cfg(data: Any) -> dict:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典对象")
    nested = data.get("agent")
    if nested is None:
        return dict(data)
    if not isinstance(nested, dict):
        raise ValueError("agent 必须是字典")
    cfg = dict(nested)
    for key, value in data.items():
        if key != "agent":
            cfg.setdefault(key, value)
    return cfg


def _pick_model_type(cfg: dict) -> tuple[Any, str]:
    raw = str(
        cfg.get("type") or cfg.get("kind") or cfg.get("provider") or ""
    ).strip().lower()
    api = str(cfg.get("api") or cfg.get("variant") or "").strip().lower()

    if raw == "dashscope" and api in ("audio", "qwen_audio", "audio_realtime"):
        raw = "dashscope_audio"
    if raw == "dashscope" and api in ("omni", "qwen_omni", "omni_realtime"):
        raw = "dashscope_omni"
    if raw == "openai" and api in ("live", "gpt_live", "gpt-live"):
        raw = "openai_live"
    if raw == "openai_realtime" and api in ("live", "gpt_live"):
        raw = "openai_live"

    cls = _MODEL_TYPES.get(raw)
    if cls is None:
        raise ValueError(
            "不支持的 realtime 类型/provider: "
            f"{raw or '(空)'}（dashscope/openai/openai_live/gemini/xai）")
    if cls in (DashScopeRealtimeModel, DashScopeAudioRealtimeModel):
        provider = "dashscope"
    elif cls in (OpenAIRealtimeModel, OpenAILiveModel):
        provider = "openai"
    elif cls is GeminiRealtimeModel:
        provider = "gemini"
    else:
        provider = "xai"
    return cls, provider


def _build_parameters(cls: Any, cfg: dict) -> Any:
    params_cls = getattr(cls, "Parameters", None)
    if params_cls is None:
        return None
    fields = set(getattr(params_cls, "model_fields", {}) or {})
    values: Dict[str, Any] = {}
    nested = cfg.get("parameters")
    if nested is not None and not isinstance(nested, dict):
        raise ValueError("realtime.parameters 必须是字典")
    values.update(nested or {})
    for key in fields:
        if key in cfg and key not in values:
            values[key] = cfg[key]
    unknown = set(values) - fields
    if unknown:
        raise ValueError(
            f"realtime.parameters 不支持的字段: {', '.join(sorted(unknown))}")
    return params_cls(**values) if values else None


def _build_vad(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, dict):
        return value
    path = value.get("class") or value.get("class_path")
    if not path:
        raise ValueError("vad 字典必须提供 class")
    module_name, _, attr = str(path).rpartition(".")
    if not module_name:
        raise ValueError("vad.class 必须是完整类路径")
    cls = getattr(importlib.import_module(module_name), attr)
    kwargs = value.get("kwargs") or {}
    if not isinstance(kwargs, dict):
        raise ValueError("vad.kwargs 必须是字典")
    return cls(**kwargs)


def _build_aggregator(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, TurnAggregator):
        return value
    if not isinstance(value, dict):
        raise ValueError("aggregator 必须是 TurnAggregator 或字典")
    kwargs = dict(value)
    if "backchannels" in kwargs and not isinstance(
            kwargs["backchannels"], frozenset):
        kwargs["backchannels"] = frozenset(kwargs["backchannels"] or [])
    allowed = {"merge_window_ms", "backchannels", "min_chars"}
    unknown = set(kwargs) - allowed
    if unknown:
        raise ValueError(
            f"aggregator 不支持的字段: {', '.join(sorted(unknown))}")
    return TurnAggregator(**kwargs)


async def async_get_realtime_model(data: dict = None) -> Dict[str, Any]:
    """从字典构建实时语音模型。"""
    fn = "async_get_realtime_model"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("data 必须是字典对象")
        cfg = data.get("llm") if isinstance(data.get("llm"), dict) else data
        model_name = str(
            cfg.get("model") or cfg.get("model_name") or "").strip()
        if not model_name:
            raise ValueError("缺少 realtime.model")
        cls, provider = _pick_model_type(cfg)

        credential = cfg.get("credential")
        if credential is None:
            credential = _build_credential(provider, cfg)
        parameters = _build_parameters(cls, cfg)

        card = cfg.get("model_card")
        if isinstance(card, dict):
            from agentscope.realtime import RealtimeModelCard

            card = RealtimeModelCard.model_validate(card)

        model = cls(
            model=model_name,
            credential=credential,
            parameters=parameters,
            model_card=card,
        )
        return _ok({
            "model": model,
            "type": type(model).__name__,
            "supports_text_input": bool(
                getattr(model, "supports_text_input", False)),
            "input_sample_rate": getattr(model, "input_sample_rate", None),
            "output_sample_rate": getattr(model, "output_sample_rate", None),
        }, "实时语音模型创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"实时语音模型创建失败：{type(e).__name__}: {e}", fn, 500)


def _build_transport(
    cfg: Any,
    model: Any = None,
) -> Any:
    if cfg is None:
        cfg = {}
    if isinstance(cfg, TransportBase):
        return cfg
    if not isinstance(cfg, dict):
        raise ValueError("transport 必须是 TransportBase 或字典")
    ttype = str(cfg.get("type") or "local").strip().lower()
    if ttype != "local":
        path = cfg.get("class") or cfg.get("class_path")
        if path:
            module_name, _, attr = str(path).rpartition(".")
            cls = getattr(importlib.import_module(module_name), attr)
            kwargs = cfg.get("kwargs") or {}
            if not isinstance(kwargs, dict):
                raise ValueError("transport.kwargs 必须是字典")
            transport = cls(**kwargs)
            if not isinstance(transport, TransportBase):
                raise ValueError("transport.class 构造结果不是 TransportBase")
            return transport
        raise ValueError(f"暂不支持的 transport.type: {ttype}（当前仅 local）")

    input_rate = cfg.get("input_sample_rate")
    output_rate = cfg.get("output_sample_rate")
    if input_rate is None:
        input_rate = getattr(model, "input_sample_rate", 16000)
    if output_rate is None:
        output_rate = getattr(model, "output_sample_rate", 24000)
    return LocalAudioTransport(
        input_sample_rate=int(input_rate),
        output_sample_rate=int(output_rate),
        input_device=cfg.get("input_device"),
        output_device=cfg.get("output_device"),
        chunk_ms=int(cfg.get("chunk_ms", 100)),
        fade_ms=int(cfg.get("fade_ms", 30)),
    )


async def async_get_realtime_transport(
    data: dict = None,
    model: Any = None,
) -> Dict[str, Any]:
    """从字典构建实时语音传输。"""
    fn = "async_get_realtime_transport"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("data 必须是字典对象")
        if isinstance(model, dict):
            r = await async_get_realtime_model(model)
            if r.get("code") != 200:
                return r
            model = r["data"]["model"]
        transport = _build_transport(
            data.get("transport", data), model=model)
        return _ok({
            "transport": transport,
            "type": type(transport).__name__,
            "closable": hasattr(transport, "close"),
        }, "实时语音传输创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"实时语音传输创建失败：{type(e).__name__}: {e}", fn, 500)


async def async_get_realtime_agent(data: dict = None) -> Dict[str, Any]:
    """从字典构建 RealtimeAgent、模型与传输。

    入参::

        {
            "agent": {
                "name": "Friday",
                "system_prompt": "你是一个中文语音助手。",
                "model": {
                    "type": "dashscope_omni",
                    "model": "qwen3.5-omni-plus-realtime",
                    "api_key": "...",
                    "parameters": {"voice": "Tina"},
                },
                "tools": ["async_sys_tools"],
                "tool_groups": {...},
                "permission": {"mode": "default"},
                "vad": None,
                "aggregator": {"merge_window_ms": 800},
                "transport": {
                    "type": "local",
                    "input_device": 3,
                    "output_device": 2,
                },
            },
        }
    """
    fn = "async_get_realtime_agent"
    try:
        cfg = _merge_agent_cfg(data)
        if not _as_bool(cfg.get("enabled"), True):
            return _ok({
                "agent": None,
                "model": None,
                "transport": None,
                "toolkit": None,
            }, "实时语音已关闭")

        name = str(cfg.get("name") or "Friday").strip()
        system_prompt = str(
            cfg.get("system_prompt") or "你是一个语音助手，回答尽量简短。")

        model = cfg.get("model") or cfg.get("realtime_model")
        if model is None:
            raise ValueError("缺少 realtime.model")
        if isinstance(model, dict):
            model_r = await async_get_realtime_model(model)
            if model_r.get("code") != 200:
                return model_r
            model = model_r["data"]["model"]
        if not isinstance(model, RealtimeModelBase):
            raise ValueError("model 必须是 RealtimeModelBase 或字典")

        toolkit = cfg.get("toolkit")
        if toolkit is None:
            spec = {
                "name": name,
                "system_prompt": system_prompt,
                "tools": cfg.get("tools"),
                "tool_groups": cfg.get("tool_groups"),
                "tool_defaults": cfg.get("tool_defaults"),
                "allow_tools": cfg.get("allow_tools"),
                "deny_tools": cfg.get("deny_tools"),
            }
            toolkit = build_subagent_toolkit(
                {k: v for k, v in spec.items() if v is not None},
                parent_toolkit=cfg.get("parent_toolkit"),
                fallback_toolkit=cfg.get("fallback_toolkit"),
            )
        if not isinstance(toolkit, Toolkit):
            raise ValueError("toolkit 必须是 Toolkit")

        state_cfg = cfg.get("state")
        if state_cfg is None:
            state = AgentState()
        elif isinstance(state_cfg, AgentState):
            state = state_cfg
        elif isinstance(state_cfg, dict):
            state = AgentState.model_validate(state_cfg)
        else:
            raise ValueError("state 必须是 AgentState 或字典")

        raw_permission = cfg.get("permission")
        if raw_permission is None:
            raw_permission = cfg.get("permission_context")
        permission_bundle = await async_build_permission_bundle(raw_permission)
        state.permission_context = permission_bundle["permission_context"]

        vad = _build_vad(cfg.get("vad"))
        aggregator = _build_aggregator(cfg.get("aggregator"))
        factory = cfg.get("delegation_agent_factory")

        agent = RealtimeAgent(
            name=name,
            system_prompt=system_prompt,
            model=model,
            toolkit=toolkit,
            state=state,
            vad=vad,
            aggregator=aggregator,
            delegation_agent_factory=factory,
        )

        transport_r = await async_get_realtime_transport(
            {"transport": cfg.get("transport") or {"type": "local"}},
            model=model,
        )
        if transport_r.get("code") != 200:
            return transport_r

        return _ok({
            "agent": agent,
            "model": model,
            "transport": transport_r["data"]["transport"],
            "toolkit": toolkit,
            "permission": permission_bundle,
            "supports_text_input": bool(
                getattr(model, "supports_text_input", False)),
        }, "RealtimeAgent 创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(
            f"RealtimeAgent 创建失败：{type(e).__name__}: {e}", fn, 500)


__all__ = [
    "async_get_realtime_model",
    "async_get_realtime_transport",
    "async_get_realtime_agent",
]
