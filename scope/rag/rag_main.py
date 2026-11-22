# -*- coding: utf-8 -*-
"""RAG 统一入口与后端分发。

当前内置后端：

- ``sqlite``：本地 SQLite + numpy 余弦检索（默认，零外部依赖）
- 其他后端通过 ``_DB_MODULES`` 注册，按其依赖是否安装懒加载；缺失时只影响该后端

统一数据契约::

    data["rag_config"] = {
        "type": "sqlite",
        "rag_function": "write|read|delete|delete_collection|list",
        "sqlite_config": {"path": "kb", "base_dir": "..."},
    }
    data["file_config"]   = {...}       # write
    data["file_chunker"]  = {...}       # write
    data["embedding"]     = {...}       # write/read（或 embedding_model 对象）
    data["search_config"] = {"query": "...", "top_k": 10, "doc_id": "..."}
    data["delete_config"] = {"doc_id": "..."}
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Dict

from .registry import record_delete, record_delete_library, record_write

# 后端名 -> 模块名（相对本包）
_DB_MODULES = {
    "sqlite": "sqlite_db",
}

_FUNC_NAMES = {
    "write": "async_write_rag_{t}",
    "read": "async_search_rag_{t}",
    "delete": "async_delete_rag_{t}",
    "delete_collection": "async_delete_collection_{t}",
    "list": "async_list_rag_{t}",
}

_LOADED: Dict[str, Any] = {}
_FAILED: Dict[str, str] = {}


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _rag_type(data: dict) -> str:
    return str((data.get("rag_config") or {}).get("type") or "sqlite").strip().lower()


def _handler(rag_type: str, function: str):
    mod = _LOADED.get(rag_type)
    if mod is None and rag_type not in _FAILED:
        module_name = _DB_MODULES.get(rag_type)
        if module_name:
            try:
                mod = importlib.import_module(f".{module_name}", __package__)
                _LOADED[rag_type] = mod
            except Exception as e:
                _FAILED[rag_type] = f"{type(e).__name__}: {e}"
    if mod is None:
        return None
    name = _FUNC_NAMES.get(function, "").format(t=rag_type)
    return getattr(mod, name, None) if name else None


def _unavailable(rag_type: str, fn: str) -> Dict[str, Any]:
    if rag_type not in _DB_MODULES:
        return _err(f"暂不支持的向量库类型：{rag_type}（当前支持: {', '.join(_DB_MODULES)}）", fn)
    reason = _FAILED.get(rag_type, "未知原因")
    return _err(f"向量库类型 {rag_type} 当前不可用（依赖加载失败：{reason}）", fn, code=500)


def _prepare(data: dict, function: str, fn: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", fn)
    rag_cfg = data.get("rag_config")
    if not isinstance(rag_cfg, dict):
        return _err("缺少 rag_config 配置段", fn)
    rag_cfg = dict(rag_cfg)
    rag_cfg.setdefault("rag_function", function)
    out = dict(data)
    out["rag_config"] = rag_cfg
    return _ok(out)


async def async_write_rag(data: dict = None) -> Dict[str, Any]:
    fn = "async_write_rag"
    try:
        prepared = _prepare(data, "write", fn)
        if prepared.get("code") != 200:
            return prepared
        prepared = prepared["data"]
        rag_type = _rag_type(prepared)
        h = _handler(rag_type, "write")
        if h is None:
            return _unavailable(rag_type, fn)
        result = await h(prepared)
        if result.get("code") == 200:
            record_write(prepared)
        return result
    except Exception as e:
        return _err(f"写入向量库失败：{type(e).__name__}: {e}", fn, code=500)


async def async_search_rag(data: dict = None) -> Dict[str, Any]:
    fn = "async_search_rag"
    try:
        prepared = _prepare(data, "read", fn)
        if prepared.get("code") != 200:
            return prepared
        prepared = prepared["data"]
        rag_type = _rag_type(prepared)
        h = _handler(rag_type, "read")
        if h is None:
            return _unavailable(rag_type, fn)
        return await h(prepared)
    except Exception as e:
        return _err(f"检索向量库失败：{type(e).__name__}: {e}", fn, code=500)


async def async_delete_rag(data: dict = None) -> Dict[str, Any]:
    fn = "async_delete_rag"
    try:
        prepared = _prepare(data, "delete", fn)
        if prepared.get("code") != 200:
            return prepared
        prepared = prepared["data"]
        rag_type = _rag_type(prepared)
        h = _handler(rag_type, "delete")
        if h is None:
            return _unavailable(rag_type, fn)
        result = await h(prepared)
        if result.get("code") == 200:
            record_delete(prepared)
        return result
    except Exception as e:
        return _err(f"删除向量数据失败：{type(e).__name__}: {e}", fn, code=500)


async def async_delete_collection(data: dict = None) -> Dict[str, Any]:
    fn = "async_delete_collection"
    try:
        prepared = _prepare(data, "delete_collection", fn)
        if prepared.get("code") != 200:
            return prepared
        prepared = prepared["data"]
        rag_type = _rag_type(prepared)
        h = _handler(rag_type, "delete_collection")
        if h is None:
            return _unavailable(rag_type, fn)
        result = await h(prepared)
        if result.get("code") == 200:
            record_delete_library(prepared)
        return result
    except Exception as e:
        return _err(f"删除向量库失败：{type(e).__name__}: {e}", fn, code=500)


async def async_list_rag(data: dict = None) -> Dict[str, Any]:
    fn = "async_list_rag"
    try:
        prepared = _prepare(data, "list", fn)
        if prepared.get("code") != 200:
            return prepared
        prepared = prepared["data"]
        rag_type = _rag_type(prepared)
        h = _handler(rag_type, "list")
        if h is None:
            return _unavailable(rag_type, fn)
        return await h(prepared)
    except Exception as e:
        return _err(f"列出向量库失败：{type(e).__name__}: {e}", fn, code=500)


async def async_rag_config(data: dict = None) -> Dict[str, Any]:
    """按 ``rag_config.rag_function``（或 ``data.function``）分发。"""
    fn = "async_rag_config"
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", fn)
    rag_cfg = data.get("rag_config")
    if not isinstance(rag_cfg, dict):
        return _err("rag_config 配置不能为空", fn)
    function = str(rag_cfg.get("rag_function") or data.get("function") or "list").strip().lower()
    routes = {
        "write": async_write_rag,
        "read": async_search_rag,
        "search": async_search_rag,
        "delete": async_delete_rag,
        "delete_collection": async_delete_collection,
        "list": async_list_rag,
    }
    handler = routes.get(function)
    if handler is None:
        return _err(f"不支持的 rag_function: {function}（write/read/delete/delete_collection/list）", fn)
    return await handler(data)


__all__ = [
    "async_write_rag",
    "async_search_rag",
    "async_delete_rag",
    "async_delete_collection",
    "async_list_rag",
    "async_rag_config",
]
