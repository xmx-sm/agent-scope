# -*- coding: utf-8 -*-
"""RAG 存储目录检查与创建。

用于 SaaS/多租户场景：先确认用户指定的 SQLite 目录是否存在；不存在时
可显式创建，而不是由后端静默 `makedirs`。

入参示例::

    await async_rag_storage_status({
        "rag_config": {
            "type": "sqlite",
            "sqlite_config": {"base_dir": "/data/tenants/u1/rag"},
        }
    })

    await async_ensure_rag_storage({
        "rag_config": {
            "type": "sqlite",
            "sqlite_config": {"base_dir": "/data/tenants/u1/rag"},
        },
        "create_dir": True,
    })
"""

from __future__ import annotations

import os
from typing import Any, Dict

try:
    from config import get as _cfg_get
except ImportError:
    from scope.config import get as _cfg_get

from ._utils import as_bool, as_dict


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _target(data: dict) -> tuple[str, str, bool]:
    """返回 (rag_type, base_dir, create_dir)。"""
    if not isinstance(data, dict):
        raise TypeError("data 必须是字典对象")
    rag_cfg = as_dict(data.get("rag_config"), "rag_config")
    rag_type = str(rag_cfg.get("type") or _cfg_get("rag.type", None) or "").strip().lower()
    if not rag_type:
        raise ValueError("缺少参数 rag_config.type（或 config.db 的 rag.type）")
    if rag_type != "sqlite":
        raise ValueError(f"当前只有 sqlite 后端需要 base_dir，收到 type={rag_type}")

    sqlite_cfg = as_dict(rag_cfg.get("sqlite_config") or data.get("sqlite_config"),
                         "sqlite_config")
    base_dir = sqlite_cfg.get("base_dir") or _cfg_get("rag.sqlite.base_dir", None)
    if not base_dir:
        raise ValueError("缺少参数 sqlite_config.base_dir（或 config.db 的 rag.sqlite.base_dir）")
    base_dir = str(base_dir)
    if not os.path.isabs(base_dir):
        raise ValueError(f"sqlite_config.base_dir 必须是绝对路径: {base_dir}")

    create_dir = data.get("create_dir")
    if create_dir is None:
        create_dir = sqlite_cfg.get("create_dir")
    if create_dir is None:
        create_dir = _cfg_get("rag.sqlite.create_dir", False)
    return rag_type, os.path.abspath(base_dir), as_bool(create_dir, "create_dir", default=False)


async def async_rag_storage_status(data: dict = None) -> Dict[str, Any]:
    """检查存储目录是否存在；不存在返回 400。"""
    fn = "async_rag_storage_status"
    try:
        rag_type, base_dir, _ = _target(data or {})
        if not os.path.isdir(base_dir):
            return _err(f"RAG 数据目录不存在: {base_dir}", fn)
        return _ok({"type": rag_type, "base_dir": base_dir, "exists": True},
                   "存储目录存在")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"检查存储目录失败：{type(e).__name__}: {e}", fn, code=500)


async def async_ensure_rag_storage(data: dict = None) -> Dict[str, Any]:
    """确保存储目录存在；create_dir=True 时自动创建。"""
    fn = "async_ensure_rag_storage"
    try:
        data = data or {}
        rag_type, base_dir, create_dir = _target(data)
        created = False
        if not os.path.isdir(base_dir):
            if not create_dir:
                return _err(
                    f"RAG 数据目录不存在: {base_dir}（如允许自动创建请传 create_dir=True）", fn)
            try:
                os.makedirs(base_dir, exist_ok=True)
                created = True
            except OSError as e:
                return _err(f"创建目录失败：{type(e).__name__}: {e}", fn, code=500)
        return _ok({"type": rag_type, "base_dir": base_dir,
                    "exists": True, "created": created},
                   "存储目录已就绪")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"准备存储目录失败：{type(e).__name__}: {e}", fn, code=500)


__all__ = ["async_rag_storage_status", "async_ensure_rag_storage"]
