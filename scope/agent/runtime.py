# -*- coding: utf-8 -*-
"""主智能体运行时：流式事件、工具审批、人机交互与中断。

设计目标：

- 主 Agent 的工具审批支持 ``allow`` / ``deny`` / ``ask``；
- ``ask`` 时优先走 ``approval_handler``；
- 没有 handler 时把 ``RequireUserConfirmEvent`` 交给调用方，
  调用方展示 UI 后通过 :meth:`AgentRuntime.resolve_confirm` 回填；
- ``interrupt()`` 可中断挂起中的确认，或取消正在运行的回复；
- 事件原样产出，前端可以按 AgentScope 的 start/delta/end 渲染。

用法::

    runtime = AgentRuntime(agent, tool_approval={"sys": "ask"})

    async for event in runtime.reply_stream(UserMsg("user", "...")):
        if isinstance(event, RequireUserConfirmEvent):
            # 推给前端，等用户选择
            await ui.show_confirm(event)
        else:
            renderer.render(event)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from agentscope.event import (
    ConfirmResult,
    ExternalExecutionResultEvent,
    RequireExternalExecutionEvent,
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
    UserInterruptEvent,
)
from agentscope.message import Msg, TextBlock, ToolResultBlock, ToolResultState


def _err(message: str, fn: str = "AgentRuntime") -> Dict[str, Any]:
    return {"code": 400, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


class AgentRuntime:
    """主 Agent 的运行时包装器。"""

    def __init__(
        self,
        agent: Any,
        *,
        tool_approval: Optional[Dict[str, str]] = None,
        approval_handler: Any = None,
        default_approval: str = "allow",
    ) -> None:
        if not hasattr(agent, "reply_stream"):
            raise ValueError("agent 必须提供 reply_stream")
        self.agent = agent
        self.tool_approval = dict(tool_approval or {})
        self.approval_handler = approval_handler
        self.default_approval = str(default_approval or "allow").lower()
        if self.default_approval not in ("allow", "deny", "ask"):
            raise ValueError("default_approval 必须是 allow/deny/ask")

        self._pending: Dict[str, dict] = {}
        self._active_task: Optional[asyncio.Task] = None
        self._interrupted = False

    # ── 审批 ────────────────────────────────────────────────────
    def _tool_group_map(self) -> Dict[str, str]:
        toolkit = getattr(self.agent, "toolkit", None)
        mapping: Dict[str, str] = {}
        for group in getattr(toolkit, "tool_groups", []) or []:
            for tool in getattr(group, "tools", []) or []:
                mapping[getattr(tool, "name", type(tool).__name__)] = group.name
        return mapping

    def _decision(self, tool_name: str, group: Optional[str],
                  policy: Optional[Dict[str, str]] = None) -> str:
        p = policy if policy is not None else self.tool_approval
        value = p.get(tool_name) or (p.get(group) if group else None) \
            or p.get("default") or self.default_approval
        value = str(value).lower()
        return value if value in ("allow", "deny", "ask") else "ask"

    def _auto_confirm(self, event: RequireUserConfirmEvent,
                      group_map: Dict[str, str],
                      policy: Optional[Dict[str, str]] = None):
        """返回 (auto_results, ask_tool_calls)。"""
        auto: Dict[str, bool] = {}
        asks: List[Any] = []
        for tc in event.tool_calls:
            name = getattr(tc, "name", "") or ""
            group = group_map.get(name)
            decision = self._decision(name, group, policy)
            if decision == "allow":
                auto[tc.id] = True
            elif decision == "deny":
                auto[tc.id] = False
            else:
                asks.append(tc)
        return auto, asks

    async def _apply_handler(self, event: RequireUserConfirmEvent,
                             asks: List[Any], group_map: Dict[str, str],
                             auto: Dict[str, bool]) -> None:
        if self.approval_handler is None:
            return
        for tc in asks:
            group = group_map.get(getattr(tc, "name", ""))
            try:
                result = self.approval_handler(tc, group, "ask")
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, dict):
                    auto[tc.id] = bool(result.get("confirmed", False))
                else:
                    auto[tc.id] = bool(result)
            except Exception:
                auto[tc.id] = False

    def pending_confirms(self) -> List[dict]:
        """当前等待用户确认的事件。"""
        return [
            {
                "reply_id": rid,
                "event": entry["event"],
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "input": tc.input}
                    for tc in entry["event"].tool_calls
                ],
            }
            for rid, entry in self._pending.items()
        ]

    def resolve_confirm(self, reply_id: str, approved: Any = None,
                        decisions: Optional[Dict[str, bool]] = None) -> bool:
        """回填挂起确认。

        approved=True/False 对所有 ask 工具生效；
        decisions={tool_id 或 tool_name: bool} 可逐个决定。
        """
        entry = self._pending.get(str(reply_id))
        if entry is None or entry["future"].done():
            return False
        entry["future"].set_result({
            "approved": approved,
            "decisions": decisions or {},
        })
        return True

    # ── 中断 ────────────────────────────────────────────────────
    async def interrupt(self, reply_id: Optional[str] = None) -> bool:
        """中断挂起确认或正在运行的回复。"""
        if self._pending:
            rid = str(reply_id) if reply_id else next(iter(self._pending))
            entry = self._pending.get(rid)
            if entry and not entry["future"].done():
                entry["future"].set_result({"interrupt": True})
                return True
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()
            return True
        return False

    # ── 回复 ────────────────────────────────────────────────────
    async def reply_stream(
        self,
        inputs: Any = None,
        *,
        tool_approval: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[Any, None]:
        """运行一轮主 Agent，产出事件 / 最终 Msg。"""
        self._active_task = asyncio.current_task()
        self._interrupted = False
        group_map = self._tool_group_map()
        final: Optional[Msg] = None
        try:
            while True:
                pending_results: List[ToolResultBlock] = []
                next_inputs: Any = None
                reply_id: Optional[str] = None

                async for evt in self.agent.reply_stream(
                        inputs=inputs, yield_final_msg=True):
                    rid = getattr(evt, "reply_id", None)
                    if rid:
                        reply_id = rid

                    if isinstance(evt, RequireUserConfirmEvent):
                        auto, asks = self._auto_confirm(
                            evt, group_map, tool_approval)
                        if asks:
                            await self._apply_handler(
                                evt, asks, group_map, auto)
                        asks_left = [
                            tc for tc in asks if tc.id not in auto
                        ]
                        if asks_left:
                            fut = asyncio.get_running_loop().create_future()
                            self._pending[evt.reply_id] = {
                                "event": evt,
                                "auto": auto,
                                "ask_ids": [tc.id for tc in asks_left],
                                "future": fut,
                            }
                            yield evt
                            ans = await fut
                            self._pending.pop(evt.reply_id, None)
                            if isinstance(ans, dict) and ans.get("interrupt"):
                                next_inputs = UserInterruptEvent(
                                    reply_id=evt.reply_id)
                                break
                            approved = (ans or {}).get("approved")
                            decisions = (ans or {}).get("decisions") or {}
                            results = []
                            for tc in evt.tool_calls:
                                if tc.id in auto:
                                    ok = auto[tc.id]
                                elif tc.id in decisions:
                                    ok = bool(decisions[tc.id])
                                elif tc.name in decisions:
                                    ok = bool(decisions[tc.name])
                                else:
                                    ok = bool(approved)
                                results.append(ConfirmResult(
                                    confirmed=ok, tool_call=tc))
                            next_inputs = UserConfirmResultEvent(
                                reply_id=evt.reply_id,
                                confirm_results=results)
                            break

                        next_inputs = UserConfirmResultEvent(
                            reply_id=evt.reply_id,
                            confirm_results=[
                                ConfirmResult(confirmed=auto.get(tc.id, False),
                                              tool_call=tc)
                                for tc in evt.tool_calls
                            ])
                        break

                    if isinstance(evt, RequireExternalExecutionEvent):
                        for tc in evt.tool_calls:
                            out = await self._call_tool(tc)
                            pending_results.append(ToolResultBlock(
                                id=tc.id, name=tc.name, output=out,
                                state=ToolResultState.SUCCESS))
                        next_inputs = ExternalExecutionResultEvent(
                            reply_id=evt.reply_id,
                            execution_results=pending_results)
                        break

                    if isinstance(evt, Msg):
                        final = evt
                    yield evt

                if next_inputs is not None:
                    inputs = next_inputs
                    continue
                break
        finally:
            self._active_task = None

    async def _call_tool(self, tool_call: Any) -> str:
        toolkit = getattr(self.agent, "toolkit", None)
        if toolkit is None:
            return "错误：agent 没有 toolkit"
        chunks = []
        async for chunk in toolkit.call_tool(tool_call, self.agent.state):
            chunks.append(chunk)
        if not chunks:
            return ""
        response = chunks[-1]
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                b.text if isinstance(b, TextBlock) else str(b) for b in content)
        return str(content or "")

    async def reply(self, inputs: Any = None, **kwargs: Any) -> Optional[Msg]:
        """消费完整事件流并返回最终 Msg。"""
        final = None
        async for evt in self.reply_stream(inputs, **kwargs):
            if isinstance(evt, Msg):
                final = evt
        return final


__all__ = ["AgentRuntime"]
