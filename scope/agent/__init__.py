# -*- coding: utf-8 -*-
"""scope.agent — 子智能体与 Agent 装配。

当前已实现：

- ``subagents.async_get_subagents``：spec 校验与工具解析
- ``delegate.async_run_subagent``：独立 AgentState 执行
- ``delegate.async_delegate_tool``：委派工具
- ``delegate.register_delegate_tool``：注册委派 / 列表 / 后台任务查询
"""

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
from .subagents import async_get_subagents, normalize_tools, resolve_tools

__all__ = [
    "AgentRuntime",
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
