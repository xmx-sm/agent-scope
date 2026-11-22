# -*- coding: utf-8 -*-
"""SOP（标准作业流程）构建器。

把字段字典转成官方 ``SOP`` / ``SOPEngine``：

- 每个步骤 = 执行者 + 可选验证者 + 最大尝试次数
- 步骤按顺序推进；驳回后只重做当前步骤
- 运行状态 ``SOPRunState`` 可持久化，恢复时传入 ``state``
- 悬起/恢复、中断由官方 ``SOPEngine.reply_stream`` 处理
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from agentscope.agent import Agent
from agentscope.sop import SOP, SOPEngine, SOPStep, SOPRunState

from .builder import async_get_agent
from .context import build_offloader


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


async def _shared_offloader(data: dict) -> Any:
    if data.get("offloader") is not None:
        return data["offloader"]
    cfg = data.get("offload") or data.get("workspace")
    if cfg is None:
        return None
    if not isinstance(cfg, dict):
        raise ValueError("offload / workspace 必须是字典")
    cfg = dict(cfg)
    cfg.setdefault("enabled", True)
    return await build_offloader({"offload": cfg})


async def _build_agent(spec: Any, default_llm: Optional[dict],
                       shared_offloader: Any, label: str) -> Agent:
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


async def async_get_sop(data: dict = None) -> Dict[str, Any]:
    """构建 SOP 与运行引擎。

    入参::

        {
            "sop": {
                "name": "write-article",
                "description": "...",
                "steps": [
                    {
                        "subject": "列出大纲",
                        "description": "至少三个章节",
                        "executor": {...agent 配置...},
                        "verifier": {...},
                        "max_attempts": 3,
                    },
                    {
                        "subject": "写正文",
                        "description": "...",
                        "executor": {...},
                    },
                ],
            },
            "llm": {...},                  # 子 Agent 默认模型
            "offload": {...},              # 共享工作区
            "state": {...}                 # 可选：恢复运行状态
        }
    """
    fn = "async_get_sop"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return _err(f"data 必须是字典对象，收到 {type(data).__name__}", fn)

        sop_cfg = data.get("sop") or data
        if not isinstance(sop_cfg, dict):
            return _err("sop 必须是字典", fn)
        name = str(sop_cfg.get("name") or "").strip()
        if not name:
            return _err("sop.name 不能为空", fn)
        raw_steps = sop_cfg.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return _err("sop.steps 必须是非空列表", fn)

        default_llm = data.get("llm") or sop_cfg.get("llm")
        offloader = await _shared_offloader(data)

        steps: List[SOPStep] = []
        for i, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                return _err(f"sop.steps[{i}] 必须是字典", fn)
            subject = str(item.get("subject") or "").strip()
            desc = str(item.get("description") or "").strip()
            if not subject or not desc:
                return _err(f"sop.steps[{i}] 缺少 subject / description", fn)
            try:
                max_attempts = int(item.get("max_attempts", 3))
            except (TypeError, ValueError):
                return _err(f"sop.steps[{i}].max_attempts 必须是整数", fn)
            if max_attempts <= 0:
                return _err(f"sop.steps[{i}].max_attempts 必须大于 0", fn)

            executor = await _build_agent(
                item.get("executor"), default_llm, offloader,
                f"sop.steps[{i}].executor")
            verifier = None
            if item.get("verifier") is not None:
                verifier = await _build_agent(
                    item.get("verifier"), default_llm, offloader,
                    f"sop.steps[{i}].verifier")
            steps.append(SOPStep(
                subject=subject,
                description=desc,
                executor=executor,
                verifier=verifier,
                max_attempts=max_attempts,
            ))

        sop = SOP(
            name=name,
            description=str(sop_cfg.get("description") or ""),
            steps=steps,
        )

        state = data.get("state")
        if isinstance(state, str):
            state = SOPRunState.model_validate_json(state)
        elif isinstance(state, dict):
            state = SOPRunState.model_validate(state)
        elif state is not None and not isinstance(state, SOPRunState):
            return _err("state 必须是 SOPRunState / dict / JSON 字符串", fn)

        engine = SOPEngine(sop, state)
        return _ok({
            "sop": sop,
            "engine": engine,
            "offloader": offloader,
        }, "SOP 创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"SOP 创建失败：{type(e).__name__}: {e}", fn, 500)


async def save_sop_state(engine: SOPEngine) -> str:
    """序列化运行状态，供持久化。"""
    return engine.state.model_dump_json()


async def load_sop_state(data: Any) -> SOPRunState:
    """从 JSON 字符串 / dict 恢复 SOPRunState。"""
    if isinstance(data, SOPRunState):
        return data
    if isinstance(data, str):
        return SOPRunState.model_validate_json(data)
    if isinstance(data, dict):
        return SOPRunState.model_validate(data)
    raise ValueError("state 必须是 SOPRunState / dict / JSON 字符串")


__all__ = ["async_get_sop", "save_sop_state", "load_sop_state"]
