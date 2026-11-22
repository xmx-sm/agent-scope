# -*- coding: utf-8 -*-
"""计划模式：TaskCreate / TaskGet / TaskList / TaskUpdate。

任务清单存放在 ``AgentState.tasks_context``，以 Agent 为作用域：

- 默认作为 ``ToolGroup("plan")`` 装配，模型通过 ``reset_tools`` 激活
- 任务工具是状态注入式，调用时直接读写 ``agent.state.tasks_context``
- 可通过 ``plan.tasks`` 预置任务（外部计划/评测/导入）
"""

from __future__ import annotations

from typing import Any, Dict, List

from agentscope.state import AgentState, Task
from agentscope.tool import (
    TaskCreate,
    TaskGet,
    TaskList,
    TaskUpdate,
    Toolkit,
    ToolGroup,
)

PLAN_GROUP_DESCRIPTION = (
    "计划模式：结构化任务清单（TaskCreate 建任务 / TaskList 看队列 / "
    "TaskGet 查详情 / TaskUpdate 改状态与依赖）。复杂多步请求需要拆解、"
    "追踪进度或表达步骤依赖时激活；任务清单随会话状态持久化。"
)
PLAN_GROUP_INSTRUCTIONS = (
    "拆任务：一步一任务，subject 一句命令式、description 写具体做什么与验收标准；"
    "开工前 TaskUpdate 置 in_progress（勿并行多个），完成后置 completed；"
    "下一步先用 TaskList 看 blocked_by，无阻塞取最小 pending id；"
    "依赖关系用 TaskUpdate 的 addBlockedBy/addBlocks 表达。"
    "单步可完成的简单请求不要建任务清单，避免噪音。"
)


def build_plan_group() -> ToolGroup:
    return ToolGroup(
        name="plan",
        description=PLAN_GROUP_DESCRIPTION,
        instructions=PLAN_GROUP_INSTRUCTIONS,
        tools=[TaskCreate(), TaskGet(), TaskList(), TaskUpdate()],
    )


def attach_plan(toolkit: Toolkit, enabled: bool) -> Toolkit:
    """把 plan 组加入/移除，保留 basic 的工具、技能、MCP 与其他组。"""
    basic = toolkit.tool_groups[0]
    groups = [g for g in toolkit.tool_groups[1:] if g.name != "plan"]
    if enabled:
        groups.append(build_plan_group())
    return Toolkit(
        tools=list(basic.tools),
        skills_or_loaders=list(basic.skills_or_loaders),
        mcps=list(basic.mcps),
        tool_groups=groups,
    )


def seed_tasks(state: AgentState, tasks: List[Dict[str, Any]]) -> None:
    """把字典任务预置到 state.tasks_context，保持依赖双向一致。"""
    if not tasks:
        return
    if state is None:
        raise ValueError("seed_tasks 需要 AgentState")
    existing = {t.id for t in state.tasks_context.tasks}
    seeded: Dict[str, Task] = {}
    for item in tasks:
        if not isinstance(item, dict):
            raise ValueError("plan.tasks 元素必须是字典")
        tid = str(item.get("id") or "").strip()
        if not tid:
            raise ValueError("plan.tasks 每项必须有 id")
        if tid in existing or tid in seeded:
            raise ValueError(f"plan.tasks 存在重复 id: {tid}")
        seeded[tid] = Task(
            id=tid,
            subject=str(item.get("subject") or ""),
            description=str(item.get("description") or ""),
            state=item.get("state") or "pending",
            owner=item.get("owner"),
            blocks=list(item.get("blocks") or []),
            blocked_by=list(item.get("blocked_by") or []),
            metadata=dict(item.get("metadata") or {}),
        )
    # 双向边一致性
    all_tasks = {t.id: t for t in state.tasks_context.tasks}
    all_tasks.update(seeded)
    for t in seeded.values():
        for b in t.blocks:
            if b in all_tasks:
                if t.id not in all_tasks[b].blocked_by:
                    all_tasks[b].blocked_by.append(t.id)
        for b in t.blocked_by:
            if b in all_tasks:
                if t.id not in all_tasks[b].blocks:
                    all_tasks[b].blocks.append(t.id)
    state.tasks_context.tasks.extend(seeded.values())


__all__ = ["build_plan_group", "attach_plan", "seed_tasks",
           "PLAN_GROUP_DESCRIPTION", "PLAN_GROUP_INSTRUCTIONS"]
