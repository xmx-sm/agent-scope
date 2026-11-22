# -*- coding: utf-8 -*-
"""scope.agent — 子智能体与 Agent 装配。

当前已实现：

- ``subagents.async_get_subagents``：spec 校验与工具解析
- ``delegate.async_run_subagent``：独立 AgentState 执行
- ``delegate.async_delegate_tool``：委派工具
- ``delegate.register_delegate_tool``：注册委派 / 列表 / 后台任务查询
- ``pipeline.async_get_pipeline``：GoalPipeline / TeamPipeline 构建
- ``sop.async_get_sop``：SOP 标准作业流程构建与状态持久化
"""

from .builder import async_get_agent
from .delegate import (
    async_cancel_subagent_task,
    async_delegate_tool,
    async_get_subagent_task,
    async_list_subagent_tasks,
    async_run_subagent,
    async_start_subagent_task,
    register_delegate_tool,
)
from .runtime import AgentRuntime
from .plan import build_plan_group, attach_plan, seed_tasks
from .pipeline import async_get_pipeline
from .sop import async_get_sop, load_sop_state, save_sop_state
from .subagents import async_get_subagents, normalize_tools, resolve_tools

__all__ = [
    "AgentRuntime",
    "async_get_agent",
    "async_get_pipeline",
    "async_get_sop",
    "save_sop_state",
    "load_sop_state",
    "build_plan_group",
    "attach_plan",
    "seed_tasks",
    "async_get_subagents",
    "resolve_tools",
    "normalize_tools",
    "async_run_subagent",
    "async_delegate_tool",
    "register_delegate_tool",
    "async_start_subagent_task",
    "async_get_subagent_task",
    "async_list_subagent_tasks",
    "async_cancel_subagent_task",
]
