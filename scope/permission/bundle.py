# -*- coding: utf-8 -*-
"""权限配置的字典总入口。

一个 ``permission`` 字典同时控制：

- 是否启用权限层（``enabled``）
- 规则与模式（``mode`` / ``allow`` / ``deny`` / ``ask`` / ``working_directories``）
- SQLite 规则持久化（``sqlite.enabled``）
- 审批审计（``audit.enabled``）
- 分布式 pending（``pending.enabled``）
- 函数级规则包装（``function_rules.enabled``）

设计原则：**所有能力默认关闭或走官方默认；必须由字典显式开启。**
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from agentscope.permission import PermissionContext

from .context import build_permission_context


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "y")
    return bool(value)


def _section(raw: Any, name: str) -> Dict[str, Any]:
    value = raw.get(name) if isinstance(raw, dict) else None
    if value is None:
        return {}
    if isinstance(value, bool):
        return {"enabled": value}
    if isinstance(value, str):
        return {"enabled": True, "path": value}
    if isinstance(value, dict):
        return dict(value)
    raise ValueError(f"permission.{name} 必须是字典、字符串或 bool")


async def async_build_permission_bundle(data: Any = None) -> Dict[str, Any]:
    """构建统一权限 bundle。

    返回::

        {
            "enabled": bool,
            "permission_context": PermissionContext,
            "store": PermissionStore | None,
            "audit": bool,
            "pending": bool,
            "pending_ttl": int,
            "function_rules": bool,
            "config": {...},          # 规范化后的可序列化配置
        }
    """
    if data is None:
        data = {}
    if isinstance(data, PermissionContext):
        return {
            "enabled": True,
            "permission_context": data,
            "store": None,
            "audit": False,
            "pending": False,
            "pending_ttl": 300,
            "function_rules": False,
            "config": {"enabled": True},
        }
    if not isinstance(data, dict):
        raise ValueError(
            "permission 必须是字典或 PermissionContext，"
            f"收到 {type(data).__name__}")

    enabled = _as_bool(data.get("enabled"), True)
    if not enabled:
        return {
            "enabled": False,
            "permission_context": PermissionContext(),
            "store": None,
            "audit": False,
            "pending": False,
            "pending_ttl": 300,
            "function_rules": False,
            "config": {"enabled": False},
        }

    sqlite_cfg = _section(data, "sqlite")
    sqlite_enabled = _as_bool(sqlite_cfg.get("enabled"), False)

    inline_config = {
        key: value for key, value in data.items()
        if key not in (
            "enabled", "sqlite", "audit", "pending",
            "function_rules", "store",
        )
    }

    store = None
    context = build_permission_context(inline_config)
    if sqlite_enabled:
        from .store import PermissionStore

        store = PermissionStore(
            sqlite_cfg.get("path"),
            create_dir=_as_bool(sqlite_cfg.get("create_dir"), False),
        )
        await store.initialize()
        context = await store.load_context(
            str(sqlite_cfg.get("tenant_id") or data.get("tenant_id") or ""),
            str(sqlite_cfg.get("agent_id") or data.get("agent_id") or ""),
            context,
        )

    audit_cfg = _section(data, "audit")
    pending_cfg = _section(data, "pending")
    audit_enabled = _as_bool(audit_cfg.get("enabled"), False)
    pending_enabled = _as_bool(pending_cfg.get("enabled"), False)
    if (audit_enabled or pending_enabled) and store is None:
        raise ValueError(
            "permission.audit / pending 开启时必须同时开启 "
            "permission.sqlite.enabled 并提供 sqlite.path")

    try:
        pending_ttl = int(pending_cfg.get("ttl_seconds", 300))
    except (TypeError, ValueError):
        raise ValueError("permission.pending.ttl_seconds 必须是整数")
    if pending_ttl <= 0:
        raise ValueError("permission.pending.ttl_seconds 必须大于 0")

    function_rules = _as_bool(
        _section(data, "function_rules").get("enabled"), False)

    config = {
        "enabled": True,
        "mode": context.mode.value,
        "sqlite": {
            "enabled": sqlite_enabled,
            "path": sqlite_cfg.get("path") if sqlite_enabled else None,
            "create_dir": _as_bool(sqlite_cfg.get("create_dir"), False),
            "tenant_id": sqlite_cfg.get("tenant_id") or data.get("tenant_id") or "",
            "agent_id": sqlite_cfg.get("agent_id") or data.get("agent_id") or "",
        },
        "audit": {"enabled": audit_enabled},
        "pending": {"enabled": pending_enabled, "ttl_seconds": pending_ttl},
        "function_rules": {"enabled": function_rules},
    }
    return {
        "enabled": True,
        "permission_context": context,
        "store": store,
        "audit": audit_enabled,
        "pending": pending_enabled,
        "pending_ttl": pending_ttl,
        "function_rules": function_rules,
        "config": config,
    }


async def async_get_permission_bundle(data: dict = None) -> Dict[str, Any]:
    """字典入口 + 统一信封。"""
    import os

    fn = "async_get_permission_bundle"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return {
                "code": 400,
                "data": f"{os.path.abspath(__file__)}_{fn}",
                "message": f"错误：data 必须是字典对象，收到 {type(data).__name__}",
            }
        raw = data.get("permission", data.get("permission_context", data))
        bundle = await async_build_permission_bundle(raw)
        return {
            "code": 200,
            "data": bundle,
            "message": "权限配置创建成功",
        }
    except (TypeError, ValueError) as e:
        return {
            "code": 400,
            "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{e}",
        }
    except Exception as e:
        return {
            "code": 500,
            "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：权限配置创建失败：{type(e).__name__}: {e}",
        }


__all__ = ["async_build_permission_bundle", "async_get_permission_bundle"]
