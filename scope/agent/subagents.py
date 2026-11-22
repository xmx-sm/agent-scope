# -*- coding: utf-8 -*-
"""子智能体 spec 校验与工具解析。

spec 全部由调用方传入（不内置模板）：

    {
        "name": "researcher",
        "description": "负责检索资料",
        "system_prompt": "你是研究员...",
        "tools": ["async_rag_tools", "async_req_tools"],  # or 函数/ToolBase
        "tool_defaults": {"async_rag_tools": {"top_k": 5}},  # 可选
        "llm": {...},          # 可选，独立模型
        "model": model_obj,    # 可选，直接复用模型对象
        "mode": "blackbox",    # blackbox / transparent / auto
        "background": false,   # 可选
        "middlewares": [...],  # 可选
        "react_config": {...}, # 可选
        "context_config": {...}, # 可选
        "permission_context": {...}, # 可选
        "tool_approval": {"sys": "ask"},  # 可选：组级/工具级 allow/deny/ask
    }

本文件只做校验和解析，不创建 Agent；实际执行在 ``delegate.py``。
"""

from __future__ import annotations

import copy
import functools
import importlib
import inspect
import os
import sys
from typing import Any, Dict, List, Optional

from agentscope.tool import FunctionTool, ToolBase, ToolGroup, Toolkit

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
            if spec.get("tool_defaults") is not None:
                if not isinstance(spec["tool_defaults"], dict):
                    return _err(f"子智能体 {name} 的 tool_defaults 必须是字典", fn)
                for tname, targs in spec["tool_defaults"].items():
                    if not isinstance(targs, dict):
                        return _err(f"子智能体 {name} 的 tool_defaults.{tname} 必须是字典", fn)
            if spec.get("tool_groups") is not None and not isinstance(
                    spec["tool_groups"], (list, dict)):
                return _err(f"子智能体 {name} 的 tool_groups 必须是列表或字典", fn)
            if spec.get("allowed_groups") is not None and not isinstance(
                    spec["allowed_groups"], (list, dict)):
                return _err(f"子智能体 {name} 的 allowed_groups 必须是列表或字典", fn)
            for fld in ("allow_tools", "allowed_tools", "deny_tools", "denied_tools"):
                if spec.get(fld) is not None and not isinstance(spec[fld], list):
                    return _err(f"子智能体 {name} 的 {fld} 必须是列表", fn)
            if spec.get("middlewares") is not None and not isinstance(spec["middlewares"], list):
                return _err(f"子智能体 {name} 的 middlewares 必须是列表", fn)
            if spec.get("tool_approval") is not None:
                if not isinstance(spec["tool_approval"], dict):
                    return _err(f"子智能体 {name} 的 tool_approval 必须是字典", fn)
                for k, v in spec["tool_approval"].items():
                    if str(v).lower() not in ("allow", "deny", "ask"):
                        return _err(
                            f"子智能体 {name} 的 tool_approval.{k} 必须是 allow/deny/ask", fn)
            result.append(spec)
        return _ok(result, f"共创建 {len(result)} 个子智能体")
    except ValueError as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"子智能体解析失败：{type(e).__name__}: {e}", fn)


def normalize_tools(tools: List[Any], defaults: Optional[Dict[str, dict]] = None) -> List[Any]:
    """函数统一包成 FunctionTool，ToolBase 原样保留。

    ``defaults`` 按工具名给默认参数：
    - 单参 ``data`` 的工具：默认值合并进 ``data`` 字典
    - 其它函数：作为顶层 kwargs 默认值
    - ToolBase 不支持注入默认参数（明确报错，避免静默失效）
    """
    defaults = defaults or {}
    out = []
    for t in tools or []:
        if isinstance(t, ToolBase):
            name = getattr(t, "name", "")
            if name in defaults:
                raise ValueError(f"工具 {name} 是 ToolBase，不支持 tool_defaults")
            out.append(t)
            continue
        if not callable(t):
            raise ValueError(f"无效工具: {type(t).__name__}")
        name = getattr(t, "__name__", "")
        tool_defaults = defaults.get(name)
        if tool_defaults is None:
            out.append(FunctionTool(t))
            continue
        if not isinstance(tool_defaults, dict):
            raise ValueError(f"tool_defaults.{name} 必须是字典")

        sig = inspect.signature(t)
        params = list(sig.parameters)

        @functools.wraps(t)
        async def _wrapped(*args, _func=t, _defaults=tool_defaults,
                           _params=params, **kwargs):
            kw = dict(kwargs)
            if _params == ["data"]:
                base = copy.deepcopy(_defaults)
                incoming = kw.get("data")
                if isinstance(incoming, dict):
                    base.update(incoming)
                    kw["data"] = base
                elif incoming is None:
                    kw["data"] = base
                else:
                    # 坏类型交给原函数自己的校验
                    kw["data"] = incoming
            else:
                merged = copy.deepcopy(_defaults)
                merged.update(kw)
                kw = merged
            res = _func(*args, **kw)
            if inspect.isawaitable(res):
                res = await res
            return res

        _wrapped.__signature__ = sig
        out.append(FunctionTool(_wrapped, name=name or None))
    return out


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", type(tool).__name__))


def _filter_tools(tools: List[Any], allow: Optional[set], deny: Optional[set]) -> List[Any]:
    out = []
    for t in tools or []:
        name = _tool_name(t)
        if allow is not None and name not in allow:
            continue
        if deny is not None and name in deny:
            continue
        out.append(t)
    return out


def _group_defs(raw: Any) -> List[dict]:
    """把 tool_groups 统一成 [{name, description?, instructions?, tools?, ...}]。"""
    if raw is None:
        return []
    items: List[dict] = []
    if isinstance(raw, dict):
        for name, value in raw.items():
            if isinstance(value, list):
                items.append({"name": name, "tools": value})
            elif isinstance(value, dict):
                items.append({"name": name, **value})
            else:
                raise ValueError(f"tool_groups.{name} 必须是列表或字典")
        return items
    if not isinstance(raw, list):
        raise ValueError("tool_groups 必须是列表或字典")
    for item in raw:
        if isinstance(item, str):
            items.append({"name": item})
        elif isinstance(item, dict):
            items.append(dict(item))
        else:
            raise ValueError(
                f"tool_groups 元素必须是字符串或字典，收到 {type(item).__name__}")
    return items


def build_subagent_toolkit(
    spec: dict,
    parent_toolkit: Optional[Toolkit] = None,
    fallback_toolkit: Optional[Toolkit] = None,
) -> Toolkit:
    """按 spec 构建子智能体专属 Toolkit。

    优先级：
        1. spec.toolkit 显式完整 Toolkit
        2. spec.tools / spec.tool_groups 构建
        3. fallback_toolkit（直接调用方显式传 data.toolkit；委派工具不传）
        4. 空 Toolkit

    tool_groups 支持：
        ["rag", "net"]                       # 从 parent_toolkit 选组
        {"rag": ["async_rag_tools"]}         # 直接定义组
        [{"name":"rag","tools":[...]}]       # 完整定义
    """
    defaults = spec.get("tool_defaults") or {}
    allow = spec.get("allow_tools", spec.get("allowed_tools"))
    deny = spec.get("deny_tools", spec.get("denied_tools"))
    allow_set = set(str(x) for x in allow) if isinstance(allow, list) else None
    deny_set = set(str(x) for x in deny) if isinstance(deny, list) else None

    explicit = spec.get("toolkit")
    if explicit is not None:
        if not isinstance(explicit, Toolkit):
            raise ValueError("spec.toolkit 必须是 Toolkit")
        return explicit

    tools_cfg = spec.get("tools")
    groups_cfg = spec.get("tool_groups", spec.get("allowed_groups"))
    if tools_cfg in (None, []) and groups_cfg in (None, [], {}):
        if fallback_toolkit is not None:
            return fallback_toolkit
        return Toolkit()

    basic_tools = normalize_tools(
        resolve_tools(tools_cfg) if tools_cfg else [], defaults)
    basic_tools = _filter_tools(basic_tools, allow_set, deny_set)

    groups: List[ToolGroup] = []
    parent_map = {g.name: g for g in (getattr(parent_toolkit, "tool_groups", []) or [])}
    for item in _group_defs(groups_cfg):
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError("tool_groups 元素缺少 name")
        if name == "basic":
            # basic 不能作为 ToolGroup 传入，合并到基本工具
            if name in parent_map:
                basic_tools.extend(_filter_tools(
                    list(parent_map[name].tools), allow_set, deny_set))
            if item.get("tools"):
                basic_tools.extend(_filter_tools(
                    normalize_tools(resolve_tools(item["tools"]), defaults),
                    allow_set, deny_set))
            continue

        if "tools" in item:
            group_tools = normalize_tools(resolve_tools(item.get("tools")), defaults)
        elif name in parent_map:
            group_tools = list(parent_map[name].tools)
        else:
            raise ValueError(f"未找到工具组: {name}（且未提供 tools 定义）")

        groups.append(ToolGroup(
            name=name,
            description=str(item.get("description") or (
                getattr(parent_map.get(name), "description", None) or name)),
            instructions=item.get("instructions") or getattr(
                parent_map.get(name), "instructions", None),
            tools=_filter_tools(group_tools, allow_set, deny_set),
            skills_or_loaders=item.get("skills_or_loaders") or list(
                getattr(parent_map.get(name), "skills_or_loaders", []) or []),
            mcps=item.get("mcps") or list(
                getattr(parent_map.get(name), "mcps", []) or []),
        ))

    return Toolkit(tools=basic_tools, tool_groups=groups)


__all__ = ["async_get_subagents", "resolve_tools", "normalize_tools",
           "build_subagent_toolkit"]
