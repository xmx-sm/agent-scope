# -*- coding: utf-8 -*-
"""按 ``data["function"]`` 细分的 FunctionTool。

官方 ``FunctionTool`` 默认只支持工具名级规则：``rule_content=None`` 匹配
整个工具，写具体内容时 ``ToolBase.match_rule`` 返回 False。本项目的大量
工具都是单入口函数，通过 ``data["function"]`` 分派多个动作，例如::

    await async_db_tools({"function": "run_query", ...})
    await async_db_tools({"function": "list_tables", ...})

``PermissionedFunctionTool`` 把 ``function`` 纳入规则匹配：

- ``rule_content=None``：整个工具，行为与官方一致
- ``rule_content="run_query"``：只匹配该 function
- ``rule_content="run_query:*"``：按 function 前缀匹配
- ``rule_content="*"``：匹配所有 function

工具名仍然是 ``async_db_tools``，所以规则配置写成::

    {
        "allow": {"async_db_tools": ["run_query", "list_tables"]},
        "deny": {"async_db_tools": ["run_sql"]},
    }

注意：这是本框架的扩展语义，只对 ``PermissionedFunctionTool`` 生效；
普通 ``FunctionTool`` / MCPTool 仍按官方语义处理。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from agentscope.permission import PermissionBehavior, PermissionRule
from agentscope.tool import FunctionTool, ToolBase


def _function_name(tool_input: Any) -> Optional[str]:
    if not isinstance(tool_input, dict):
        return None
    value = tool_input.get("function") or tool_input.get("function_name")
    if value is None and isinstance(tool_input.get("data"), dict):
        value = tool_input["data"].get("function") \
            or tool_input["data"].get("function_name")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _match_function(pattern: Optional[str], name: Optional[str]) -> bool:
    if pattern is None:
        return True
    if not name:
        return False
    text = str(pattern).strip()
    if text in ("", "*"):
        return True
    if text.endswith(":*"):
        return name.startswith(text[:-2])
    if text.endswith("*"):
        return name.startswith(text[:-1])
    if text.startswith("*"):
        return name.endswith(text[1:])
    return name == text


class PermissionedFunctionTool(FunctionTool):
    """支持 ``data["function"]`` 级 allow/deny/ask 的 FunctionTool。"""

    async def match_rule(
        self,
        rule_content: str | None,
        tool_input: dict[str, Any],
    ) -> bool:
        if rule_content is None:
            return True
        return _match_function(rule_content, _function_name(tool_input))

    async def generate_suggestions(
        self,
        tool_input: dict[str, Any],
    ) -> List[PermissionRule]:
        name = _function_name(tool_input)
        return [
            PermissionRule(
                tool_name=self.name,
                rule_content=name,
                behavior=PermissionBehavior.ALLOW,
                source="suggested",
            ),
        ]


def wrap_permissioned_tool(tool: Any) -> Any:
    """把普通函数 / FunctionTool 转成 PermissionedFunctionTool。

    - ``PermissionedFunctionTool`` 原样返回
    - ``FunctionTool`` 复制其配置后重新包装，尽量保留 name/description/schema
    - 普通可调用对象直接包装
    - 其它 ``ToolBase`` 原样返回
    """
    if isinstance(tool, PermissionedFunctionTool):
        return tool
    if isinstance(tool, FunctionTool):
        return PermissionedFunctionTool(
            func=tool._func,
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            is_concurrency_safe=tool.is_concurrency_safe,
            is_read_only=tool.is_read_only,
            is_state_injected=tool.is_state_injected,
            middlewares=tool._middlewares,
            permission=getattr(tool, "_permission", None),
        )
    if isinstance(tool, ToolBase):
        return tool
    if callable(tool):
        return PermissionedFunctionTool(tool)
    raise ValueError(f"无法包装为工具: {type(tool).__name__}")


def wrap_permissioned_tools(tools: Iterable[Any]) -> List[Any]:
    """批量包装工具。"""
    return [wrap_permissioned_tool(tool) for tool in tools or []]


__all__ = [
    "PermissionedFunctionTool",
    "wrap_permissioned_tool",
    "wrap_permissioned_tools",
]
