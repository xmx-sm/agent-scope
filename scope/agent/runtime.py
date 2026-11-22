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

try:
    from ..permission import build_permission_context, set_permission_mode
    from ..permission.store import make_pending_key
except ImportError:
    from permission import build_permission_context, set_permission_mode
    from permission.store import make_pending_key


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
        audit_store: Any = None,
        pending_store: Any = None,
        tenant_id: str = "",
        agent_id: str = "",
        pending_ttl: Optional[int] = None,
        permission: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not hasattr(agent, "reply_stream"):
            raise ValueError("agent 必须提供 reply_stream")
        self.agent = agent
        self.tool_approval = dict(tool_approval or {})
        self.approval_handler = approval_handler
        self.default_approval = str(default_approval or "allow").lower()
        if self.default_approval not in ("allow", "deny", "ask"):
            raise ValueError("default_approval 必须是 allow/deny/ask")

        bundle = permission
        if not isinstance(bundle, dict):
            bundle = getattr(agent, "_scope_permission", None)
        if not isinstance(bundle, dict):
            bundle = {}
        self.permission = bundle
        config = bundle.get("config") if isinstance(bundle.get("config"), dict) else {}
        sqlite_cfg = config.get("sqlite") if isinstance(config.get("sqlite"), dict) else {}
        pending_cfg = config.get("pending") if isinstance(config.get("pending"), dict) else {}

        store = bundle.get("store")
        self.audit_store = (
            audit_store if audit_store is not None
            else (store if bundle.get("audit") else None)
        )
        self.pending_store = (
            pending_store if pending_store is not None
            else (store if bundle.get("pending") else None)
        )
        self.tenant_id = str(
            tenant_id or sqlite_cfg.get("tenant_id") or "")
        self.agent_id = str(
            agent_id or sqlite_cfg.get("agent_id") or "")
        ttl = pending_ttl
        if ttl is None:
            ttl = bundle.get("pending_ttl") or pending_cfg.get("ttl_seconds") or 300
        self.pending_ttl = max(1, int(ttl))
        self._pending: Dict[str, dict] = {}
        self._active_task: Optional[asyncio.Task] = None
        self._interrupted = False

    # ── 权限 ────────────────────────────────────────────────────
    def _permission_context(self):
        state = getattr(self.agent, "state", None)
        context = getattr(state, "permission_context", None)
        if context is None:
            context = build_permission_context()
            if state is not None:
                state.permission_context = context
        return context

    def permission_context(self):
        """当前 Agent 的 PermissionContext。"""
        return self._permission_context()

    def set_permission_mode(self, mode: Any) -> str:
        """运行时切换权限模式，返回规范化后的模式名。"""
        return set_permission_mode(self._permission_context(), mode).value

    async def _record_audit(
        self,
        tool_call: Any,
        *,
        confirmed: bool,
        reply_id: Optional[str],
        decision_source: str,
        rules: Any = None,
    ) -> None:
        if self.audit_store is None:
            return
        if rules is None:
            rule_list = []
        elif isinstance(rules, (list, tuple)):
            rule_list = list(rules)
        else:
            rule_list = [rules]
        entry = {
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "reply_id": reply_id,
            "tool_call_id": getattr(tool_call, "id", None),
            "tool_name": getattr(tool_call, "name", "") or "",
            "tool_input": getattr(tool_call, "input", None),
            "decision": "allow" if confirmed else "deny",
            "decision_source": decision_source,
            "rules": [
                rule.model_dump(mode="json")
                for rule in rule_list
                if hasattr(rule, "model_dump")
            ],
        }
        try:
            result = self.audit_store.record_audit(entry)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            # 审计失败不能阻断主流程；生产环境应接入日志/重试。
            return

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
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.input,
                        "suggested_rules": [
                            rule.model_dump(mode="json")
                            for rule in (getattr(tc, "suggested_rules", None) or [])
                        ],
                    }
                    for tc in entry["event"].tool_calls
                ],
            }
            for rid, entry in self._pending.items()
        ]

    def _pending_payload(self, event: RequireUserConfirmEvent) -> dict:
        return {
            "reply_id": event.reply_id,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                    "suggested_rules": [
                        rule.model_dump(mode="json")
                        for rule in (getattr(tc, "suggested_rules", None) or [])
                    ],
                }
                for tc in event.tool_calls
            ],
        }

    async def list_pending_confirms(self) -> List[dict]:
        """列出 pending；配置 pending_store 时读取跨进程共享记录。"""
        if self.pending_store is not None:
            items = await self.pending_store.list_pending(
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                status="pending",
            )
            return items
        return self.pending_confirms()

    async def _wait_answer(
        self,
        future: asyncio.Future,
        pending_key: Optional[str],
    ) -> Any:
        if self.pending_store is None or pending_key is None:
            return await future

        poll = asyncio.create_task(
            self.pending_store.wait_pending(
                pending_key,
                timeout=float(self.pending_ttl),
                interval=0.5,
            ),
        )
        try:
            done, _ = await asyncio.wait(
                {future, poll}, return_when=asyncio.FIRST_COMPLETED)
            if future in done:
                poll.cancel()
                return future.result()
            answer = poll.result()
            if answer is None:
                answer = {"approved": False}
            if not future.done():
                future.set_result(answer)
            return answer
        finally:
            if not poll.done():
                poll.cancel()

    def resolve_confirm(self, reply_id: str, approved: Any = None,
                        decisions: Optional[Dict[str, bool]] = None,
                        accept_suggested_rules: bool = False) -> bool:
        """回填挂起确认。

        approved=True/False 对所有 ask 工具生效；
        decisions={tool_id 或 tool_name: bool} 可逐个决定。
        accept_suggested_rules=True 时，会被接受的工具调用把官方生成的
        建议规则一并回传，后续相同调用不再询问。
        """
        entry = self._pending.get(str(reply_id))
        if entry is None or entry["future"].done():
            return False
        payload = {
            "approved": approved,
            "decisions": decisions or {},
            "accept_suggested_rules": bool(accept_suggested_rules),
        }
        entry["future"].set_result(payload)
        if self.pending_store is not None and entry.get("pending_key"):
            try:
                asyncio.get_running_loop().create_task(
                    self.pending_store.resolve_pending(
                        entry["pending_key"], payload,
                        expected_version=entry.get("pending_version"),
                    ),
                )
            except RuntimeError:
                pass
        return True

    async def resolve_confirm_async(self, reply_id: str, approved: Any = None,
                                    decisions: Optional[Dict[str, bool]] = None,
                                    accept_suggested_rules: bool = False) -> bool:
        """异步回填；使用 pending_store 时确保结果已落库。"""
        entry = self._pending.get(str(reply_id))
        if entry is None or entry["future"].done():
            return False
        payload = {
            "approved": approved,
            "decisions": decisions or {},
            "accept_suggested_rules": bool(accept_suggested_rules),
        }
        if self.pending_store is not None and entry.get("pending_key"):
            await self.pending_store.resolve_pending(
                entry["pending_key"], payload,
                expected_version=entry.get("pending_version"),
            )
        entry["future"].set_result(payload)
        return True

    # ── 中断 ────────────────────────────────────────────────────
    async def interrupt(self, reply_id: Optional[str] = None) -> bool:
        """中断挂起确认或正在运行的回复。"""
        if self._pending:
            rid = str(reply_id) if reply_id else next(iter(self._pending))
            entry = self._pending.get(rid)
            if entry and not entry["future"].done():
                entry["future"].set_result({"interrupt": True})
                if self.pending_store is not None and entry.get("pending_key"):
                    try:
                        asyncio.get_running_loop().create_task(
                            self.pending_store.resolve_pending(
                                entry["pending_key"], {"interrupt": True}),
                        )
                    except RuntimeError:
                        pass
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
                            pending_key = None
                            if self.pending_store is not None:
                                pending_key = make_pending_key(
                                    evt.reply_id,
                                    tenant_id=self.tenant_id,
                                    agent_id=self.agent_id,
                                )
                                try:
                                    await self.pending_store.save_pending(
                                        pending_key,
                                        self._pending_payload(evt),
                                        tenant_id=self.tenant_id,
                                        agent_id=self.agent_id,
                                        reply_id=evt.reply_id,
                                        ttl_seconds=self.pending_ttl,
                                    )
                                except Exception:
                                    pending_key = None
                            fut = asyncio.get_running_loop().create_future()
                            self._pending[evt.reply_id] = {
                                "event": evt,
                                "auto": auto,
                                "ask_ids": [tc.id for tc in asks_left],
                                "future": fut,
                                "pending_key": pending_key,
                            }
                            yield evt
                            ans = await self._wait_answer(fut, pending_key)
                            self._pending.pop(evt.reply_id, None)
                            if isinstance(ans, dict) and ans.get("interrupt"):
                                next_inputs = UserInterruptEvent(
                                    reply_id=evt.reply_id)
                                break
                            approved = (ans or {}).get("approved")
                            decisions = (ans or {}).get("decisions") or {}
                            accept_rules = bool(
                                (ans or {}).get("accept_suggested_rules"))
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
                                rules = None
                                if ok and accept_rules:
                                    rules = getattr(tc, "suggested_rules", None) or None
                                await self._record_audit(
                                    tc,
                                    confirmed=ok,
                                    reply_id=evt.reply_id,
                                    decision_source=("policy" if tc.id in auto else "user"),
                                    rules=rules,
                                )
                                results.append(ConfirmResult(
                                    confirmed=ok, tool_call=tc, rules=rules))
                            next_inputs = UserConfirmResultEvent(
                                reply_id=evt.reply_id,
                                confirm_results=results)
                            break

                        results = []
                        for tc in evt.tool_calls:
                            confirmed = bool(auto.get(tc.id, False))
                            await self._record_audit(
                                tc,
                                confirmed=confirmed,
                                reply_id=evt.reply_id,
                                decision_source="policy",
                            )
                            results.append(ConfirmResult(
                                confirmed=confirmed, tool_call=tc))
                        next_inputs = UserConfirmResultEvent(
                            reply_id=evt.reply_id,
                            confirm_results=results)
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
