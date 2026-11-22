# -*- coding: utf-8 -*-
"""主 Agent 构建器。

把模型、Toolkit、上下文配置、中间件、状态组装成 Agent。所有配置都走字典：

    await async_get_agent({
        "llm": {...},
        "agent": {
            "name": "assistant",
            "system_prompt": "...",
            "toolkit": toolkit,
            "context_config": {...},
            "injection_config": {...},
            "offload": {"enabled": True, "workdir": "/data/workspace"},
        },
    })
"""

from __future__ import annotations

import os
from typing import Any, Dict

from agentscope.agent import (
    Agent,
    ContextConfig,
    InjectionConfig,
    ModelConfig,
    ReActConfig,
)
from agentscope.permission import PermissionContext
from agentscope.state import AgentState
from agentscope.tool import Toolkit

try:
    from ..llm.agent_model import async_get_llm_model
except ImportError:
    from llm.agent_model import async_get_llm_model

from .context import build_context_bundle


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _coerce(value: Any, cls: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, cls):
        return value
    if isinstance(value, dict):
        try:
            return cls.model_validate(value)
        except Exception as e:
            raise ValueError(f"{name} 配置非法：{e}") from e
    raise ValueError(f"{name} 必须是 {cls.__name__} 或字典，收到 {type(value).__name__}")


async def async_get_agent(data: dict = None) -> Dict[str, Any]:
    """构建主 Agent。

    入参:
        llm(dict, 可选)              模型配置；未传则用 agent.model / data.model
        agent(dict, 可选)            Agent 配置：
            name / system_prompt / toolkit / middlewares / state
            context_config / injection_config / offload / offloader
            react_config / model_config / permission_context
    """
    fn = "async_get_agent"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return _err(f"data 必须是字典对象，收到 {type(data).__name__}", fn)
        agent_cfg = data.get("agent")
        if agent_cfg is None:
            agent_cfg = {}
        if not isinstance(agent_cfg, dict):
            return _err("agent 必须是字典", fn)

        model = agent_cfg.get("model") or data.get("model")
        if model is None:
            llm_cfg = data.get("llm") or agent_cfg.get("llm")
            if not isinstance(llm_cfg, dict) or not llm_cfg:
                return _err("缺少模型配置：data.model / agent.model / data.llm", fn)
            r = await async_get_llm_model({"llm": llm_cfg})
            if r.get("code") != 200:
                return r
            model = r["data"]

        toolkit = agent_cfg.get("toolkit") or data.get("toolkit")
        if toolkit is None:
            toolkit = Toolkit()
        if not isinstance(toolkit, Toolkit):
            return _err("toolkit 必须是 Toolkit 实例", fn)

        bundle = await build_context_bundle(data)
        context_config = bundle["context_config"] or ContextConfig()
        injection_config = bundle["injection_config"] or InjectionConfig()
        offloader = bundle["offloader"]

        react_config = _coerce(
            agent_cfg.get("react_config") or data.get("react_config"),
            ReActConfig, "react_config")
        model_config = _coerce(
            agent_cfg.get("model_config") or data.get("model_config"),
            ModelConfig, "model_config")
        permission_context = _coerce(
            agent_cfg.get("permission_context") or data.get("permission_context"),
            PermissionContext, "permission_context")

        state_cfg = agent_cfg.get("state") or data.get("state")
        if state_cfg is None:
            state = AgentState(permission_context=permission_context or PermissionContext())
        else:
            state = _coerce(state_cfg, AgentState, "state")

        middlewares = agent_cfg.get("middlewares") or data.get("middlewares") or []
        if not isinstance(middlewares, list):
            return _err("middlewares 必须是列表", fn)

        agent = Agent(
            name=str(agent_cfg.get("name") or "assistant"),
            system_prompt=str(agent_cfg.get("system_prompt") or "你是一个智能助手。"),
            model=model,
            toolkit=toolkit,
            middlewares=middlewares or None,
            state=state,
            offloader=offloader,
            model_config=model_config,
            context_config=context_config,
            react_config=react_config,
            injection_config=injection_config,
        )
        return _ok({
            "agent": agent,
            "context_config": context_config,
            "injection_config": injection_config,
            "offloader": offloader,
        }, "Agent 初始化成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"Agent 初始化失败：{type(e).__name__}: {e}", fn, 500)


__all__ = ["async_get_agent"]
