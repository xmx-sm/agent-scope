# -*- coding: utf-8 -*-
"""主 Agent 上下文配置解析。

三块能力：

- **上下文压缩**：``ContextConfig``
- **运行时状态注入**：``InjectionConfig``
- **上下文卸载**：``Offloader``（当前实现 LocalWorkspace）

优先级统一为：

    data（agent.context_config / context 等）
      > config.db（agent.context.* / agent.injection.* / agent.offload.*）
      > AgentScope 默认

配置值可以是对象，也可以是字典；字典会先补齐 config.db 默认值再构造。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from agentscope.agent import ContextConfig, InjectionConfig

try:
    from config import get as _cfg_get
except ImportError:
    from scope.config import get as _cfg_get


_CONTEXT_KEYS = (
    "trigger_ratio",
    "reserve_ratio",
    "context_buffer_ratio",
    "tool_result_limit",
    "max_image_num",
    "compression_tool_enabled",
    "compression_fallback_to_truncation",
)
_INJECTION_KEYS = (
    "inject_runtime_state",
    "timezone",
    "time_format",
    "time_interval",
    "tool_retries_limit",
    "emit_hint_event",
)


def _agent_cfg(data: dict) -> dict:
    cfg = data.get("agent") if isinstance(data, dict) else None
    return cfg if isinstance(cfg, dict) else {}


def _defaults(keys, prefix: str) -> Dict[str, Any]:
    return {k: _cfg_get(f"{prefix}.{k}", None) for k in keys}


def build_context_config(data: dict = None) -> Optional[ContextConfig]:
    data = data or {}
    agent = _agent_cfg(data)
    raw = (
        agent.get("context_config")
        or data.get("context_config")
        or data.get("context")
    )
    if raw is None:
        raw = {}
    if isinstance(raw, ContextConfig):
        return raw
    if not isinstance(raw, dict):
        raise ValueError("context_config 必须是字典或 ContextConfig")

    merged = {}
    for k, v in _defaults(_CONTEXT_KEYS, "agent.context").items():
        if v is not None:
            merged[k] = v
    merged.update(raw)
    for k in ("compression_prompt", "summary_template", "summary_schema"):
        if k in raw:
            merged[k] = raw[k]
    return ContextConfig(**merged)


def build_injection_config(data: dict = None) -> Optional[InjectionConfig]:
    data = data or {}
    agent = _agent_cfg(data)
    raw = (
        agent.get("injection_config")
        or data.get("injection_config")
        or data.get("injection")
    )
    if raw is None:
        raw = {}
    if isinstance(raw, InjectionConfig):
        return raw
    if not isinstance(raw, dict):
        raise ValueError("injection_config 必须是字典或 InjectionConfig")

    merged = {}
    for k, v in _defaults(_INJECTION_KEYS, "agent.injection").items():
        if v is not None:
            merged[k] = v
    merged.update(raw)
    for k in ("template", "tool_retries_hint", "task_tool_names",
              "injection_source", "extra_fields"):
        if k in raw:
            merged[k] = raw[k]
    return InjectionConfig(**merged)


async def build_offloader(data: dict = None) -> Any:
    """构建上下文卸载器；未开启返回 None。"""
    data = data or {}
    agent = _agent_cfg(data)
    raw = agent.get("offloader") or data.get("offloader")
    if raw is not None:
        if not hasattr(raw, "offload_context"):
            raise ValueError("offloader 必须实现 offload_context")
        return raw

    cfg = agent.get("offload") or data.get("offload")
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError("offload 配置必须是字典")

    enabled = cfg.get("enabled")
    if enabled is None:
        enabled = _cfg_get("agent.offload.enabled", False)
    workdir = cfg.get("workdir") or _cfg_get("agent.offload.workdir", None)
    if not enabled and not workdir:
        return None
    if not workdir:
        raise ValueError("启用上下文卸载时必须提供 offload.workdir")
    if not os.path.isabs(str(workdir)):
        raise ValueError(f"offload.workdir 必须是绝对路径: {workdir}")
    offload_type = str(cfg.get("type") or _cfg_get("agent.offload.type", "local")).lower()
    if offload_type != "local":
        raise ValueError(f"暂不支持的 offload.type: {offload_type}（当前仅 local）")

    from agentscope.workspace import LocalWorkspace
    kwargs: Dict[str, Any] = {"workdir": os.path.abspath(str(workdir))}
    for key in ("workspace_id", "instructions", "skill_paths",
                "default_mcps", "max_live_stateful_mcps"):
        if cfg.get(key) is not None:
            kwargs[key] = cfg[key]
    workspace = LocalWorkspace(**kwargs)
    await workspace.initialize()
    return workspace


async def build_context_bundle(data: dict = None) -> Dict[str, Any]:
    """一次性构建三块上下文配置。"""
    return {
        "context_config": build_context_config(data),
        "injection_config": build_injection_config(data),
        "offloader": await build_offloader(data),
    }


__all__ = [
    "build_context_config",
    "build_injection_config",
    "build_offloader",
    "build_context_bundle",
]
