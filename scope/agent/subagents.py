# -*- coding: utf-8 -*-
"""子智能体 spec 校验与工具解析。

spec 全部由调用方传入（不内置模板）：

    {
        "name": "researcher",
        "description": "负责检索资料",
        "system_prompt": "你是研究员...",
        "tools": ["async_rag_tools", "async_req_tools"],  # or 函数/ToolBase
        "llm": {...},          # 可选，独立模型
        "mode": "blackbox",    # blackbox / transparent / auto
        "background": false,   # 可选
    }

本文件只做校验和解析，不创建 Agent；实际执行在 ``delegate.py``。
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Dict, List

from agentscope.tool import FunctionTool, ToolBase

_WHERE_FILE = os.path.abspath(__file__)
# 兼容 scope.agent 包导入：工具域使用顶层 ``from config import ...``，
# 需要把 scope/ 目录加入 sys.path（与 README 的装配方式一致）。
_SCOPE_DIR = os.path.dirname(os.path.dirname(_WHERE_FILE))
if _SCOPE_DIR not in sys.path:
    sys.path.insert(0, _SCOPE_DIR)

# 字符串工具名 -> (模块, 属性名)
_TOOL_IMPORTS = {
    "async_req_tools": ("tools.net.main_net", "async_req_tools"),
    "async_crawl_tools": ("tools.net.main_crawl", "async_crawl_tools"),
    "async_email_tools": ("tools.mail.main_mail", "async_email_tools"),
    "async_db_tools": ("tools.db.main_db", "async_db_tools"),
    "async_db_write_tools": ("tools.db.main_db", "async_db_write_tools"),
    "async_rag_tools": ("tools.rag.main_rag", "async_rag_tools"),
    "async_sys_tools": ("tools.system.main_sys", "async_sys_tools"),
    "async_mcp_tools": ("tools.mcp.main_mcp", "async_mcp_tools"),
    # 兼容旧名
    "req_tools": ("tools.net.main_net", "async_req_tools"),
    "crawl_tools": ("tools.net.main_crawl", "async_crawl_tools"),
    "email_tools": ("tools.mail.main_mail", "async_email_tools"),
    "db_tools": ("tools.db.main_db", "async_db_tools"),
    "db_write_tools": ("tools.db.main_db", "async_db_write_tools"),
    "rag_tools": ("tools.rag.main_rag", "async_rag_tools"),
    "sys_tools": ("tools.system.main_sys", "async_sys_tools"),
    "mcp_tools": ("tools.mcp.main_mcp", "async_mcp_tools"),
}


def _where(fn: str) -> str:
    return f"{_WHERE_FILE}_{fn}"


def _err(message: str, fn: str) -> Dict[str, Any]:
    return {"code": 400, "data": _where(fn), "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _load_tool(name: str) -> Any:
    module, attr = _TOOL_IMPORTS[name]
    try:
        mod = importlib.import_module(module)
    except ImportError:
        mod = importlib.import_module("scope." + module)
    return getattr(mod, attr)


def resolve_tools(tools: Any) -> List[Any]:
    """把 spec.tools 解析成函数 / ToolBase 列表。"""
    if tools is None:
        return []
    if not isinstance(tools, list):
        raise ValueError("subagent.tools 必须是列表")
    result: List[Any] = []
    for item in tools:
        if isinstance(item, str):
            if item not in _TOOL_IMPORTS:
                raise ValueError(
                    f"未定义的工具名: {item}，支持: {', '.join(sorted(_TOOL_IMPORTS))}")
            try:
                result.append(_load_tool(item))
            except Exception as e:
                raise ValueError(f"工具 {item} 加载失败：{type(e).__name__}: {e}") from e
        elif isinstance(item, ToolBase) or callable(item):
            result.append(item)
        else:
            raise ValueError(
                f"tools 元素类型不支持: {type(item).__name__}（支持字符串 / 函数 / ToolBase）")
    return result


async def async_get_subagents(data: dict = None) -> Dict[str, Any]:
    """校验并规范化子智能体 spec 列表。

    入参 ``data["subagents"]``：spec 列表；为空返回空列表。
    每个 spec 必填 ``name`` / ``system_prompt``；``description`` 缺省用 name；
    ``tools`` 缺省空列表。
    """
    fn = "async_get_subagents"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", fn)
    raw = data.get("subagents")
    if raw in (None, "", []):
        return _ok([], "未配置子智能体，返回空列表")
    if not isinstance(raw, list):
        return _err("subagents 必须是列表", fn)

    try:
        result: List[Dict[str, Any]] = []
        seen = set()
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                return _err(f"subagents[{i}] 必须是字典", fn)
            name = str(item.get("name") or "").strip()
            system_prompt = str(item.get("system_prompt") or "").strip()
            if not name:
                return _err(f"subagents[{i}] 缺少 name", fn)
            if name in seen:
                return _err(f"子智能体名称重复: {name}", fn)
            seen.add(name)
            if not system_prompt:
                return _err(f"子智能体 {name} 缺少 system_prompt", fn)

            mode = str(item.get("mode") or "auto").strip().lower()
            if mode not in ("blackbox", "transparent", "auto"):
                return _err(
                    f"子智能体 {name} 的 mode 不支持: {mode}（blackbox/transparent/auto）", fn)

            spec = dict(item)
            spec["name"] = name
            spec["description"] = str(item.get("description") or name)
            spec["system_prompt"] = system_prompt
            spec["tools"] = resolve_tools(item.get("tools"))
            spec["mode"] = mode
            spec["background"] = bool(item.get("background", False))
            if spec.get("llm") is not None and not isinstance(spec["llm"], dict):
                return _err(f"子智能体 {name} 的 llm 必须是字典", fn)
            if spec.get("toolkit") is not None and not hasattr(spec["toolkit"], "add_tool"):
                return _err(f"子智能体 {name} 的 toolkit 无效", fn)
            result.append(spec)
        return _ok(result, f"共创建 {len(result)} 个子智能体")
    except ValueError as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"子智能体解析失败：{type(e).__name__}: {e}", fn)


def normalize_tools(tools: List[Any]) -> List[Any]:
    """函数统一包成 FunctionTool，ToolBase 原样保留。"""
    out = []
    for t in tools or []:
        if isinstance(t, ToolBase):
            out.append(t)
        elif callable(t):
            out.append(FunctionTool(t))
        else:
            raise ValueError(f"无效工具: {type(t).__name__}")
    return out


__all__ = ["async_get_subagents", "resolve_tools", "normalize_tools"]
