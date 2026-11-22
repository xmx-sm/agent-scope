# -*- coding: utf-8 -*-
"""流水线构建器：GoalPipeline / TeamPipeline。

流水线是 AgentScope 的多智能体组合方式：

- ``GoalPipeline``：执行者产出 → 验证者判定 → 不通过带理由重做
- ``TeamPipeline``：队长通过 ``TeamAssign`` 把任务分派给成员

本文件只负责从字典构建 Agent 并组装流水线；运行仍使用官方
``pipeline.reply_stream(...)``。流水线内部所有 Agent 的事件共用同一个
``reply_stream`` 出口，HITL 事件也由官方流水线处理。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from agentscope.agent import Agent
from agentscope.pipeline import GoalPipeline, TeamMember, TeamPipeline

from .builder import async_get_agent
from .context import build_offloader


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


async def _shared_offloader(data: dict) -> Any:
    """流水线级共享工作区；GoalPipeline 的执行者/验证者必须共享才能看见产出。"""
    if data.get("offloader") is not None:
        return data["offloader"]
    cfg = data.get("offload") or data.get("workspace")
    if cfg is None:
        return None
    if not isinstance(cfg, dict):
        raise ValueError("offload / workspace 必须是字典")
    cfg = dict(cfg)
    if "enabled" not in cfg:
        cfg["enabled"] = True
    return await build_offloader({"offload": cfg})


async def _build_agent(
    spec: Any,
    *,
    default_llm: Optional[dict],
    shared_offloader: Any,
    label: str,
) -> Agent:
    if isinstance(spec, Agent):
        return spec
    if not isinstance(spec, dict):
        raise ValueError(f"{label} 必须是 Agent 或字典")
    cfg = dict(spec)
    if "agent" not in cfg:
        cfg = {"agent": cfg}
    if default_llm and not cfg.get("llm") and not cfg["agent"].get("llm"):
        cfg["llm"] = default_llm
    if shared_offloader is not None and cfg.get("offloader") is None \
            and cfg["agent"].get("offloader") is None:
        cfg["offloader"] = shared_offloader
    r = await async_get_agent(cfg)
    if r.get("code") != 200:
        raise ValueError(r.get("message") or f"{label} 构建失败")
    return r["data"]["agent"]


async def async_get_pipeline(data: dict = None) -> Dict[str, Any]:
    """从字典构建流水线。

    入参::

        {
            "type": "goal",
            "executor": {...agent 配置或 Agent...},
            "verifier": {...},
            "verifier_reset_context": True,
            "max_iters": 10,
            "max_retries": 3,
            "offload": {"enabled": True, "workdir": "/data/workspace"},
        }

        {
            "type": "team",
            "leader": {...},
            "members": [
                {"agent": {...}, "description": "负责检索"},
                {"agent": Agent, "description": "负责写代码"},
            ],
            "reset_members": True,
            "offload": {...},
        }
    """
    fn = "async_get_pipeline"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return _err(f"data 必须是字典对象，收到 {type(data).__name__}", fn)

        pipe_type = str(data.get("type") or "").strip().lower()
        if pipe_type not in ("goal", "team"):
            return _err(f"type 必须是 goal 或 team，收到 {pipe_type or '(空)'}", fn)

        default_llm = data.get("llm")
        offloader = await _shared_offloader(data)

        if pipe_type == "goal":
            executor = await _build_agent(
                data.get("executor"), default_llm=default_llm,
                shared_offloader=offloader, label="executor")
            verifier = await _build_agent(
                data.get("verifier"), default_llm=default_llm,
                shared_offloader=offloader, label="verifier")
            try:
                max_iters = int(data.get("max_iters", 10))
                max_retries = int(data.get("max_retries", 3))
            except (TypeError, ValueError):
                return _err("max_iters / max_retries 必须是整数", fn)
            if max_iters <= 0 or max_retries <= 0:
                return _err("max_iters / max_retries 必须大于 0", fn)
            pipeline = GoalPipeline(
                executor=executor,
                verifier=verifier,
                verifier_reset_context=bool(data.get("verifier_reset_context", True)),
                max_iters=max_iters,
                max_retries=max_retries,
            )
            return _ok({
                "pipeline": pipeline,
                "type": "goal",
                "executor": executor,
                "verifier": verifier,
                "offloader": offloader,
            }, "GoalPipeline 创建成功")

        leader = await _build_agent(
            data.get("leader"), default_llm=default_llm,
            shared_offloader=offloader, label="leader")
        raw_members = data.get("members")
        if not isinstance(raw_members, list) or not raw_members:
            return _err("members 必须是非空列表", fn)
        members: List[TeamMember] = []
        built_members: List[Agent] = []
        for i, item in enumerate(raw_members):
            if not isinstance(item, dict):
                return _err(f"members[{i}] 必须是字典", fn)
            agent_spec = item.get("agent")
            if agent_spec is None:
                return _err(f"members[{i}] 缺少 agent", fn)
            desc = str(item.get("description") or "").strip()
            if not desc:
                return _err(f"members[{i}] 缺少 description", fn)
            agent = await _build_agent(
                agent_spec, default_llm=default_llm,
                shared_offloader=offloader, label=f"members[{i}]")
            members.append(TeamMember(agent=agent, description=desc))
            built_members.append(agent)

        pipeline = TeamPipeline(
            leader=leader,
            members=members,
            reset_members=bool(data.get("reset_members", True)),
        )
        return _ok({
            "pipeline": pipeline,
            "type": "team",
            "leader": leader,
            "members": built_members,
            "offloader": offloader,
        }, "TeamPipeline 创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"流水线创建失败：{type(e).__name__}: {e}", fn, 500)


__all__ = ["async_get_pipeline"]
