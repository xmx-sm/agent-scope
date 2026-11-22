# -*- coding: utf-8 -*-
"""权限层：官方 PermissionContext 的字典构建与运行时辅助。

AgentScope 的权限决策仍由 ``PermissionEngine`` 完成；本包只负责：

- 把中文业务侧常用的 allow / deny / ask 字典转成 ``PermissionContext``
- 运行时切换 ``PermissionMode``
- 输出可 JSON 序列化的权限配置
- 把权限上下文接入 Agent / 子智能体工厂
- 按 ``data["function"]`` 细分工具规则
- SQLite 保存规则、审批审计与跨进程 pending

不复制官方规则匹配、只读判定或工具安全检查逻辑。
"""

from .context import (
    add_permission_rule,
    async_build_permission_context,
    async_get_permission_context,
    build_permission_context,
    merge_permission_context,
    parse_permission_mode,
    permission_context_to_dict,
    set_permission_mode,
)
from .tool import (
    PermissionedFunctionTool,
    wrap_permissioned_tool,
    wrap_permissioned_tools,
)
from .store import PermissionStore, make_pending_key
from .bundle import (
    async_build_permission_bundle,
    async_get_permission_bundle,
)

__all__ = [
    "add_permission_rule",
    "async_build_permission_bundle",
    "async_build_permission_context",
    "async_get_permission_bundle",
    "async_get_permission_context",
    "build_permission_context",
    "merge_permission_context",
    "parse_permission_mode",
    "permission_context_to_dict",
    "set_permission_mode",
    "PermissionedFunctionTool",
    "wrap_permissioned_tool",
    "wrap_permissioned_tools",
    "PermissionStore",
    "make_pending_key",
]
