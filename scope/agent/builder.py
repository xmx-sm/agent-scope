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
import sys
from typing import Any, Dict

from agentscope.agent import (
    Agent,
    ContextConfig,
    InjectionConfig,
    ModelConfig,
    ReActConfig,
)
from agentscope.mcp import MCPClient
from agentscope.state import AgentState
from agentscope.tool import Toolkit

_SCOPE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCOPE_DIR not in sys.path:
    sys.path.insert(0, _SCOPE_DIR)

try:
    from ..llm.agent_model import async_get_llm_model
except ImportError:
    from llm.agent_model import async_get_llm_model

try:
    from ..skills.loader import build_skills
except ImportError:
    from skills.loader import build_skills

try:
    from ..permission import build_permission_context
except ImportError:
    from permission import build_permission_context

try:
    from config import get as _cfg_get
except ImportError:
    from scope.config import get as _cfg_get

from .context import build_context_bundle
try:
    from .plan import attach_plan, seed_tasks
except ImportError:
    from plan import attach_plan, seed_tasks


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


def _attach_mcps(toolkit: Toolkit, clients: list) -> Toolkit:
    if not clients:
        return toolkit
    basic = toolkit.tool_groups[0]
    groups = toolkit.tool_groups[1:]
    return Toolkit(
        tools=list(basic.tools),
        skills_or_loaders=list(basic.skills_or_loaders),
        mcps=list(basic.mcps) + list(clients),
        tool_groups=groups,
    )


def _mcp_enabled(agent_cfg: dict, data: dict, cfg: Any) -> bool:
    raw = agent_cfg.get("mcp_enabled")
    if raw is None:
        raw = data.get("mcp_enabled")
    if raw is None and isinstance(cfg, dict) and "enabled" in cfg:
        raw = cfg.get("enabled")
    if raw is None:
        raw = _cfg_get("agent.mcp.enabled", True)
    return _as_bool(raw, True)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on", "y"):
            return True
        if s in ("0", "false", "no", "off", "n", ""):
            return False
    raise ValueError(f"布尔开关非法：{value!r}")


def _attach_skills(toolkit: Toolkit, skills: list) -> Toolkit:
    basic = toolkit.tool_groups[0]
    groups = toolkit.tool_groups[1:]
    return Toolkit(
        tools=list(basic.tools),
        skills_or_loaders=list(skills),
        mcps=list(basic.mcps),
        tool_groups=groups,
    )


async def _build_mcps(cfg: Any, enabled: bool = True) -> Dict[str, Any]:
    """把字典配置转成 MCPClient 列表；支持 True / dict / list[MCPClient]。"""
    if not enabled or cfg is None or cfg is False or cfg == "":
        return _ok([])
    if isinstance(cfg, list):
        if not all(isinstance(c, MCPClient) for c in cfg):
            return _err("mcps 列表元素必须是 MCPClient", "async_get_agent")
        return _ok(list(cfg))
    if isinstance(cfg, dict):
        cfg = dict(cfg)
        cfg.pop("enabled", None)
        if "servers" in cfg and "mcpServers" not in cfg:
            cfg = {"mcpServers": cfg.get("servers") or {}}
    try:
        from tools.mcp.client import async_mcp_client
    except ImportError as e:
        return _err(f"MCP 模块加载失败：{e}", "async_get_agent")
    r = await async_mcp_client({"mcp": cfg})
    if r.get("code") != 200:
        return r
    return _ok(r.get("data") or [])


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

        tools_cfg = agent_cfg.get("tools") if isinstance(agent_cfg.get("tools"), dict) else {}
        mcp_cfg = (
            agent_cfg.get("mcp")
            or agent_cfg.get("mcps")
            or tools_cfg.get("mcp")
            or data.get("mcp")
            or data.get("mcps")
        )
        mcp_r = await _build_mcps(mcp_cfg, enabled=_mcp_enabled(agent_cfg, data, mcp_cfg))
        if mcp_r.get("code") != 200:
            return mcp_r
        mcp_clients = mcp_r.get("data") or []
        toolkit = _attach_mcps(toolkit, mcp_clients)

        skills_present = agent_cfg.get("skills") is not None or data.get("skills") is not None
        skills_r = await build_skills(data)
        if skills_r.get("code") != 200:
            return skills_r
        skills = skills_r.get("data") or []
        if skills_present or skills:
            toolkit = _attach_skills(toolkit, skills)

        plan_cfg = agent_cfg.get("plan") or data.get("plan")
        if plan_cfg is None:
            plan_cfg = {}
        if not isinstance(plan_cfg, dict):
            return _err("plan 必须是字典", fn)
        plan_present = agent_cfg.get("plan") is not None or data.get("plan") is not None
        plan_raw = agent_cfg.get("plan_enabled")
        if plan_raw is None:
            plan_raw = data.get("plan_enabled")
        if plan_raw is None:
            plan_raw = plan_cfg.get("enabled")
        if plan_raw is None:
            plan_raw = _cfg_get("agent.plan.enabled", False)
        plan_enabled = _as_bool(plan_raw, False)
        if plan_present or plan_enabled:
            toolkit = attach_plan(toolkit, plan_enabled)

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
        raw_permission = agent_cfg.get("permission_context")
        if raw_permission is None:
            raw_permission = data.get("permission_context")
        permission_context = (
            build_permission_context(raw_permission)
            if raw_permission is not None else None
        )

        state_cfg = agent_cfg.get("state") or data.get("state")
        if state_cfg is None:
            state = AgentState(
                permission_context=permission_context or build_permission_context())
        else:
            state = _coerce(state_cfg, AgentState, "state")
            if permission_context is not None:
                state.permission_context = permission_context

        tasks = plan_cfg.get("tasks") or agent_cfg.get("tasks") or data.get("tasks")
        if tasks is not None:
            if not isinstance(tasks, list):
                return _err("plan.tasks 必须是列表", fn)
            try:
                seed_tasks(state, tasks)
            except ValueError as e:
                return _err(str(e), fn)

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
            "mcps": mcp_clients,
            "skills": skills,
        }, "Agent 初始化成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"Agent 初始化失败：{type(e).__name__}: {e}", fn, 500)


__all__ = ["async_get_agent"]
