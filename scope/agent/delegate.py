# -*- coding: utf-8 -*-
"""子智能体执行与委派工具。

主 Agent 通过 ``async_delegate_tool`` 把任务下发给子智能体。子智能体使用
独立 ``AgentState``，不污染主会话上下文。

执行形态：
    blackbox     只返回最终结论
    transparent  返回结论 + 子智能体完整对话记录
    auto         默认按 blackbox 行为

不内置任何子智能体模板：spec 必须由调用方通过 ``data["subagents"]`` 传入。
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from agentscope.agent import (
    Agent,
    ContextConfig,
    InjectionConfig,
    ModelConfig,
    ReActConfig,
)
from agentscope.event import (
    ConfirmResult,
    ExternalExecutionResultEvent,
    RequireExternalExecutionEvent,
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
)
from agentscope.message import Msg, TextBlock, ToolResultBlock, ToolResultState
from agentscope.permission import PermissionContext
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit

try:
    from ..llm.agent_model import async_get_llm_model
except ImportError:
    from llm.agent_model import async_get_llm_model

from .subagents import async_get_subagents, build_subagent_toolkit

_WHERE_FILE = os.path.abspath(__file__)


def _where(fn: str) -> str:
    return f"{_WHERE_FILE}_{fn}"


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _reply_text(msg: Any) -> str:
    if msg is None:
        return ""
    if hasattr(msg, "get_text_content"):
        try:
            text = msg.get_text_content()
            if text:
                return text
        except Exception:
            pass
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, TextBlock):
                parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content or "")


def _state_history(agent: Agent) -> List[dict]:
    history = []
    for msg in getattr(agent.state, "context", []) or []:
        history.append({
            "role": getattr(msg, "role", ""),
            "name": getattr(msg, "name", ""),
            "text": _reply_text(msg),
        })
    return history


async def _collect_tool_response(toolkit: Toolkit, tool_call: Any, agent: Agent) -> str:
    chunks = []
    async for chunk in toolkit.call_tool(tool_call, agent.state):
        chunks.append(chunk)
    if not chunks:
        return ""
    response = chunks[-1]
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            parts.append(block.text if isinstance(block, TextBlock) else str(block))
        return "\n".join(parts)
    return str(content or "")


async def _run_reply_loop(agent: Agent, toolkit: Toolkit, inputs: Any) -> Any:
    """驱动子 agent 完整跑一轮，处理外部执行与确认事件。"""
    final = None
    while True:
        pending_results, pending_confirms, reply_id = [], [], None
        async for evt in agent.reply_stream(inputs=inputs, yield_final_msg=True):
            if isinstance(evt, Msg):
                final = evt
            elif isinstance(evt, RequireExternalExecutionEvent):
                reply_id = evt.reply_id
                for tc in evt.tool_calls:
                    out = await _collect_tool_response(toolkit, tc, agent)
                    pending_results.append(ToolResultBlock(
                        id=tc.id, name=tc.name, output=out,
                        state=ToolResultState.SUCCESS,
                    ))
            elif isinstance(evt, RequireUserConfirmEvent):
                reply_id = evt.reply_id
                # 子智能体默认自动确认；如需真正审批，应由 permission 层接管
                for tc in evt.tool_calls:
                    pending_confirms.append(ConfirmResult(confirmed=True, tool_call=tc))

        if pending_results:
            inputs = ExternalExecutionResultEvent(
                reply_id=reply_id, execution_results=pending_results)
        elif pending_confirms:
            inputs = UserConfirmResultEvent(
                reply_id=reply_id, confirm_results=pending_confirms)
        else:
            break
    return final


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

async def _build_subagent(spec: dict, data: dict) -> Dict[str, Any]:
    model = data.get("model") or spec.get("model")
    if model is None:
        llm_cfg = data.get("llm") or spec.get("llm") or data.get("default_llm")
        if not isinstance(llm_cfg, dict) or not llm_cfg:
            return _err(f"子智能体 {spec.get('name')} 缺少模型配置（llm/default_llm/model）",
                        "async_run_subagent")
        r = await async_get_llm_model({"llm": llm_cfg})
        if r.get("code") != 200:
            return _err(f"子智能体模型初始化失败：{r.get('message')}", "async_run_subagent")
        model = r["data"]

    try:
        toolkit = build_subagent_toolkit(
            spec,
            parent_toolkit=data.get("parent_toolkit"),
            fallback_toolkit=data.get("toolkit"),
        )
    except (TypeError, ValueError) as e:
        return _err(str(e), "async_run_subagent")

    try:
        middlewares = spec.get("middlewares") or data.get("middlewares") or []
        if not isinstance(middlewares, list):
            raise ValueError("middlewares 必须是列表")

        context_config = _coerce(
            data.get("context_config") or spec.get("context_config"),
            ContextConfig, "context_config")
        react_config = _coerce(
            data.get("react_config") or spec.get("react_config"),
            ReActConfig, "react_config")
        model_config = _coerce(
            data.get("model_config") or spec.get("model_config"),
            ModelConfig, "model_config")
        injection_config = _coerce(
            data.get("injection_config") or spec.get("injection_config"),
            InjectionConfig, "injection_config")
        permission_context = _coerce(
            spec.get("permission_context") or data.get("permission_context"),
            PermissionContext, "permission_context")

        state_cfg = spec.get("state") or data.get("state")
        if state_cfg is None:
            state = AgentState(permission_context=permission_context or PermissionContext())
        else:
            state = _coerce(state_cfg, AgentState, "state")

        agent = Agent(
            name=spec.get("name"),
            system_prompt=spec.get("system_prompt"),
            model=model,
            toolkit=toolkit,
            middlewares=middlewares or None,
            state=state,
            model_config=model_config,
            react_config=react_config,
            context_config=context_config,
            injection_config=injection_config,
        )
        return _ok({"agent": agent, "toolkit": toolkit})
    except (TypeError, ValueError) as e:
        return _err(str(e), "async_run_subagent")


async def async_run_subagent(data: dict = None) -> Dict[str, Any]:
    """执行一个子智能体任务。

    入参:
        subagent(str, 必填)      子智能体名字
        task(str, 必填)          任务描述
        subagents(list, 必填)    完整 spec 列表
        mode(str, 可选)          blackbox/transparent/auto
        model(对象, 可选)        复用模型对象
        llm(dict, 可选)          独立模型配置
        default_llm(dict, 可选)  缺省模型配置
        toolkit(对象, 可选)      子智能体工具包
        background(bool, 可选)   后台执行
        owner(str, 可选)         任务属主（后台查询用）
    """
    fn = "async_run_subagent"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return _err(f"data 必须是字典对象，收到 {type(data).__name__}", fn)

        subagent = str(data.get("subagent") or "").strip()
        task = data.get("task")
        if not subagent:
            return _err("缺少 subagent 参数", fn)
        if not isinstance(task, str) or not task.strip():
            return _err("缺少 task 参数（任务描述）", fn)

        raw_specs = data.get("subagents")
        if raw_specs in (None, "", []):
            return _err(f"未配置子智能体，无法委派: {subagent}", fn)
        specs_r = await async_get_subagents({"subagents": raw_specs})
        if specs_r.get("code") != 200:
            return specs_r
        specs = specs_r["data"]
        spec = next((s for s in specs if s.get("name") == subagent), None)
        if spec is None:
            names = ", ".join(s.get("name", "") for s in specs) or "无"
            return _err(f"未找到子智能体: {subagent}（可用: {names}）", fn)

        if (data.get("background") or spec.get("background")) and not data.get("force_foreground"):
            return await async_start_subagent_task(data)

        built = await _build_subagent(spec, data)
        if built.get("code") != 200:
            return built
        agent, toolkit = built["data"]["agent"], built["data"]["toolkit"]

        mode = str(data.get("mode") or spec.get("mode") or "auto").strip().lower()
        if mode not in ("blackbox", "transparent", "auto"):
            return _err(f"不支持的 mode: {mode}（blackbox/transparent/auto）", fn)

        final = await _run_reply_loop(
            agent, toolkit, Msg(name="user", role="user", content=[TextBlock(text=task)]))
        reply = _reply_text(final)
        out: Dict[str, Any] = {
            "name": spec.get("name"),
            "task": task,
            "mode": mode,
            "reply": reply,
        }
        if mode == "transparent":
            out["history"] = _state_history(agent)
        return _ok(out, "子智能体执行完成")
    except Exception as e:
        return _err(f"子智能体执行失败：{type(e).__name__}: {e}", fn, code=500)


# ── 后台任务注册表 ──────────────────────────────────────────────
_TASKS: Dict[str, dict] = {}
_TASK_TTL = 3600.0
_TASK_MAX = 200


def _prune_tasks() -> None:
    now = time.monotonic()
    finished = []
    for tid, entry in list(_TASKS.items()):
        if entry.get("status") not in ("done", "failed"):
            continue
        at = entry.get("_finished_mono")
        if at is not None and now - at > _TASK_TTL:
            _TASKS.pop(tid, None)
            continue
        finished.append((at or 0.0, tid))
    overflow = len(_TASKS) - _TASK_MAX
    if overflow > 0:
        finished.sort()
        for _, tid in finished[:overflow]:
            _TASKS.pop(tid, None)


def _visible(entry: dict, owner: str | None) -> bool:
    entry_owner = entry.get("owner")
    return not entry_owner or entry_owner == owner


async def _task_runner(task_id: str, run_data: dict) -> None:
    entry = _TASKS.get(task_id)
    if entry is None:
        return
    entry["status"] = "running"
    try:
        result = await async_run_subagent(run_data)
        entry["result"] = result
        entry["status"] = "done" if result.get("code") == 200 else "failed"
        if result.get("code") != 200:
            entry["error"] = result.get("message")
    except Exception as e:
        entry["status"] = "failed"
        entry["error"] = f"{type(e).__name__}: {e}"
    finally:
        entry["finished_at"] = datetime.now(timezone.utc).isoformat()
        entry["_finished_mono"] = time.monotonic()


async def async_start_subagent_task(data: dict = None) -> Dict[str, Any]:
    """后台启动子智能体任务，立即返回 task_id。"""
    fn = "async_start_subagent_task"
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", fn)
    run_data = dict(data)
    run_data["background"] = False
    run_data["force_foreground"] = True
    task_id = uuid.uuid4().hex
    _prune_tasks()
    _TASKS[task_id] = {
        "task_id": task_id,
        "subagent": run_data.get("subagent"),
        "task": run_data.get("task"),
        "mode": run_data.get("mode"),
        "owner": run_data.get("owner"),
        "status": "pending",
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    _TASKS[task_id]["_asyncio_task"] = asyncio.create_task(_task_runner(task_id, run_data))
    return _ok({"task_id": task_id, "subagent": run_data.get("subagent"),
                "status": "running"}, f"后台任务已启动: {task_id}")


def _public(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def async_get_subagent_task(task_id: str, owner: str = None) -> Dict[str, Any]:
    """按 task_id 查询后台任务。"""
    _prune_tasks()
    entry = _TASKS.get(str(task_id or ""))
    if entry is None or not _visible(entry, owner):
        return _err(f"任务不存在: {task_id}", "async_get_subagent_task")
    return _ok(_public(entry), "ok")


def async_list_subagent_tasks(limit: int = 50, owner: str = None) -> Dict[str, Any]:
    """列出最近的后台任务。"""
    _prune_tasks()
    entries = [e for e in _TASKS.values() if _visible(e, owner)]
    entries.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return _ok([_public(e) for e in entries[:max(1, int(limit))]], "ok")


async def async_delegate_tool(data: dict = None) -> Dict[str, Any]:
    """子智能体委派工具（可直接作为 FunctionTool）。"""
    result = await async_run_subagent(data)
    if result.get("code") != 200:
        return result
    return _ok(result.get("data") or {}, "子智能体执行完成")


async def register_delegate_tool(
    toolkit: Toolkit,
    default_llm: dict = None,
    name: str = None,
    subagents: list = None,
    register_task_tool: bool = True,
    owner: str = None,
) -> None:
    """把委派工具 / 子智能体列表 / 后台任务查询注册进主 Toolkit。"""
    catalog = []
    for s in subagents or []:
        if isinstance(s, dict) and s.get("name"):
            desc = str(s.get("description") or "").strip()
            catalog.append(f"- {s['name']}" + (f"：{desc}" if desc else ""))
    catalog_text = ("当前可用的子智能体目录（subagent 只能取以下名字）：\n"
                    + "\n".join(catalog)) if catalog else "当前没有已配置的子智能体。"

    async def _delegate(subagent: str = None, task: str = None,
                        mode: str = None, background: bool = None) -> dict:
        """
        把任务下发给指定子智能体，返回其最终回复。子智能体在独立上下文中运行。

        {catalog}

        :param subagent: [必填] 子智能体名字，只能取上方目录中的名字
        :param task: [必填] 任务描述
        :param mode: [选填] blackbox/transparent/auto
        :param background: [选填] true=后台执行，立即返回 task_id
        :return: 统一信封
        """
        payload = {
            "subagent": subagent,
            "task": task,
            "parent_toolkit": toolkit,
        }
        if mode:
            payload["mode"] = mode
        if background is not None:
            payload["background"] = bool(background)
        if subagents:
            payload["subagents"] = subagents
        if default_llm:
            payload["default_llm"] = default_llm
        if owner:
            payload["owner"] = owner
        return await async_delegate_tool(payload)

    _delegate.__doc__ = _delegate.__doc__.replace("{catalog}", catalog_text)
    await toolkit.add_tool(FunctionTool(
        _delegate, name=name or "async_delegate_tool",
        is_read_only=False, is_concurrency_safe=False))

    async def _list() -> dict:
        """列出当前可委派的子智能体。"""
        items = [{
            "name": s.get("name"),
            "description": s.get("description"),
            "mode": s.get("mode") or "auto",
            "background": bool(s.get("background")),
        } for s in (subagents or []) if isinstance(s, dict) and s.get("name")]
        return _ok(items, f"共 {len(items)} 个子智能体" if items else "当前没有已配置的子智能体")

    await toolkit.add_tool(FunctionTool(
        _list, name="subagent_list", is_read_only=True))

    if register_task_tool:
        async def _task_status(task_id: str = None) -> dict:
            """查询后台子智能体任务；不传 task_id 返回最近任务列表。"""
            if task_id:
                return async_get_subagent_task(task_id, owner=owner)
            return async_list_subagent_tasks(owner=owner)

        await toolkit.add_tool(FunctionTool(
            _task_status, name="subagent_task_status", is_read_only=True))


__all__ = [
    "async_run_subagent",
    "async_delegate_tool",
    "register_delegate_tool",
    "async_start_subagent_task",
    "async_get_subagent_task",
    "async_list_subagent_tasks",
]
