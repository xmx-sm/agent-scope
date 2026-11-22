# -*- coding: utf-8 -*-
"""后端统一入口。

后端不需要分别 import 各模块，只需调用::

    r = await async_dispatch({
        "domain": "rag",
        "action": "tools",
        "data": {
            "function": "read",
            "rag_config": {...},
            "search_config": {"query": "..."},
        },
    })

约定：

- 所有入参都是字典
- 所有返回值都是 ``{"code", "data", "message"}``
- object 类型结果（Agent / Model / Workspace / Middleware）只在同进程
  后端中直接使用；如果要通过 HTTP 返回，需要上层做 session registry
- 这里不引入新的业务逻辑，只做统一路由

路由表：

    domain=tool        action=db|net|mail|mcp|system
    domain=rag         action=tools|config|knowledge_base|middleware
    domain=llm         action=chat|embedding|tts|asr
    domain=media       action=tts|asr
    domain=agent       action=create|subagents|pipeline|sop
    domain=permission  action=context|store
    domain=middleware  action=build
    domain=workspace   action=create
    domain=realtime    action=model|transport|agent
    domain=config      action=get|set|all|categories|items
    domain=system      action=ping|capabilities
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Dict

_SCOPE_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCOPE_DIR not in sys.path:
    sys.path.insert(0, _SCOPE_DIR)


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _err(message: str, fn: str = "async_dispatch", code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": f"{_where(fn)}", "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _payload(data: dict) -> dict:
    value = data.get("data")
    if value is None:
        value = data.get("payload")
    if value is None:
        value = data.get("params")
    return value if isinstance(value, dict) else {}


async def _tool(action: str, payload: dict) -> Dict[str, Any]:
    modules = {
        "db": ("tools.db.main_db", "async_db_tools"),
        "net": ("tools.net.main_net", "async_req_tools"),
        "mail": ("tools.mail.main_mail", "async_email_tools"),
        "mcp": ("tools.mcp.main_mcp", "async_mcp_tools"),
        "system": ("tools.system.main_sys", "async_sys_tools"),
        "rag": ("tools.rag.main_rag", "async_rag_tools"),
    }
    target = modules.get(action)
    if target is None:
        return _err(f"未知 tool: {action}")
    module_name, attr = target
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        module = importlib.import_module("scope." + module_name)
    return await getattr(module, attr)(payload)


async def _rag(action: str, payload: dict) -> Dict[str, Any]:
    if action == "tools":
        from scope.tools.rag.main_rag import async_rag_tools

        return await async_rag_tools(payload)
    if action == "config":
        from scope.rag.rag_main import async_rag_config

        return await async_rag_config(payload)
    if action in ("knowledge_base", "kb"):
        from scope.rag.knowledge import async_create_knowledge_base

        return await async_create_knowledge_base(payload)
    if action == "middleware":
        from scope.rag.knowledge import async_create_rag_middleware

        return await async_create_rag_middleware(payload)
    return _err(f"未知 rag action: {action}")


async def _llm(action: str, payload: dict) -> Dict[str, Any]:
    from scope.llm import (
        async_get_asr_model,
        async_get_embedding_model,
        async_get_llm_model,
        async_get_tts_model,
    )

    handlers = {
        "chat": async_get_llm_model,
        "embedding": async_get_embedding_model,
        "tts": async_get_tts_model,
        "asr": async_get_asr_model,
    }
    handler = handlers.get(action)
    if handler is None:
        return _err(f"未知 llm action: {action}")
    return await handler(payload)


async def _media(action: str, payload: dict) -> Dict[str, Any]:
    if action == "tts":
        from scope.media.tts import async_generate_tts

        return await async_generate_tts(payload)
    if action == "asr":
        from scope.media.asr import async_transcribe_asr

        return await async_transcribe_asr(payload)
    return _err(f"未知 media action: {action}")


async def _agent(action: str, payload: dict) -> Dict[str, Any]:
    if action == "create":
        from scope.agent.builder import async_get_agent

        return await async_get_agent(payload)
    if action == "subagents":
        from scope.agent.subagents import async_get_subagents

        return await async_get_subagents(payload)
    if action == "pipeline":
        from scope.agent.pipeline import async_get_pipeline

        return await async_get_pipeline(payload)
    if action == "sop":
        from scope.agent.sop import async_get_sop

        return await async_get_sop(payload)
    return _err(f"未知 agent action: {action}")


async def _permission(action: str, payload: dict) -> Dict[str, Any]:
    if action == "context":
        from scope.permission import async_get_permission_context

        return await async_get_permission_context(payload)
    if action == "store":
        from scope.permission.store import PermissionStore

        cfg = payload.get("sqlite") or payload.get("store") or payload
        store = PermissionStore(
            cfg.get("path"),
            create_dir=bool(cfg.get("create_dir", False)),
        )
        await store.initialize()
        return _ok({"store": store}, "PermissionStore 创建成功")
    return _err(f"未知 permission action: {action}")


async def _middleware(action: str, payload: dict) -> Dict[str, Any]:
    if action == "build":
        from scope.middleware import async_get_middlewares

        return await async_get_middlewares(payload)
    if action == "memory":
        from scope.middleware import async_get_memory

        return await async_get_memory(payload)
    return _err(f"未知 middleware action: {action}")


async def _workspace(action: str, payload: dict) -> Dict[str, Any]:
    if action == "create":
        from scope.workspace import async_get_workspace

        return await async_get_workspace(payload)
    return _err(f"未知 workspace action: {action}")


async def _realtime(action: str, payload: dict) -> Dict[str, Any]:
    from scope.realtime import (
        async_get_realtime_agent,
        async_get_realtime_model,
        async_get_realtime_transport,
    )

    handlers = {
        "model": async_get_realtime_model,
        "transport": async_get_realtime_transport,
        "agent": async_get_realtime_agent,
    }
    handler = handlers.get(action)
    if handler is None:
        return _err(f"未知 realtime action: {action}")
    return await handler(payload)


async def _config(action: str, payload: dict) -> Dict[str, Any]:
    from scope import config

    if action == "get":
        key = payload.get("key") or payload.get("name")
        if not key:
            return _err("缺少 key")
        return _ok(config.get(str(key), payload.get("default")))
    if action == "set":
        key = payload.get("key") or payload.get("name")
        if not key:
            return _err("缺少 key")
        ok = config.set_value(
            str(key), payload.get("value"),
            persist=bool(payload.get("persist", True)),
        )
        return _ok(ok, "配置已写入" if ok else "配置写入失败")
    if action in ("all", "values"):
        return _ok(config.all_values())
    if action == "categories":
        return _ok(config.categories())
    if action == "items":
        category = payload.get("category")
        return _ok([
            {
                "key": item.key,
                "default": item.default,
                "type": item.type,
                "category": item.category,
                "description": item.description,
            }
            for item in config.items_by_category(category)
        ])
    return _err(f"未知 config action: {action}")


async def _system(action: str, payload: dict) -> Dict[str, Any]:
    if action == "ping":
        return _ok({"ok": True})
    if action == "capabilities":
        return _ok({
            "tool": ["db", "net", "mail", "mcp", "system", "rag"],
            "rag": ["tools", "config", "knowledge_base", "middleware"],
            "llm": ["chat", "embedding", "tts", "asr"],
            "media": ["tts", "asr"],
            "agent": ["create", "subagents", "pipeline", "sop"],
            "permission": ["context", "store"],
            "middleware": ["build", "memory"],
            "workspace": ["create"],
            "realtime": ["model", "transport", "agent"],
            "config": ["get", "set", "all", "categories", "items"],
            "system": ["ping", "capabilities"],
        })
    return _err(f"未知 system action: {action}")


async def async_dispatch(data: dict = None) -> Dict[str, Any]:
    """后端统一路由入口。

    入参::

        {"domain": "rag", "action": "tools", "data": {...}}
        {"module": "rag", "action": "tools", "payload": {...}}   # 别名

    返回统一信封。``domain=tool`` 时 action 是工具域。
    """
    fn = "async_dispatch"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err(f"data 必须是字典对象，收到 {type(data).__name__}", fn)

    domain = str(
        data.get("domain") or data.get("module") or data.get("type") or ""
    ).strip().lower()
    action = str(data.get("action") or data.get("function") or "").strip().lower()
    if not domain:
        return _err("缺少 domain", fn)
    if not action:
        return _err("缺少 action", fn)

    payload = _payload(data)
    handlers = {
        "tool": _tool,
        "rag": _rag,
        "llm": _llm,
        "media": _media,
        "agent": _agent,
        "permission": _permission,
        "middleware": _middleware,
        "workspace": _workspace,
        "realtime": _realtime,
        "config": _config,
        "system": _system,
    }
    handler = handlers.get(domain)
    if handler is None:
        return _err(
            f"未知 domain: {domain}（{', '.join(sorted(handlers))}）", fn)
    try:
        return await handler(action, payload)
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"{domain}.{action} 执行失败：{type(e).__name__}: {e}", fn, 500)


async def async_handle(data: dict = None) -> Dict[str, Any]:
    """``async_dispatch`` 的别名。"""
    return await async_dispatch(data)


__all__ = ["async_dispatch", "async_handle"]
