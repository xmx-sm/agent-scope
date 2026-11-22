# -*- coding: utf-8 -*-
"""跨层文件读写闸门。

媒体落盘（``scope/media``）与 RAG 文档读取（``scope/rag``）共用同一个策略：

- 平台可注入 ``check_write(path) -> (bool, str)`` / ``check_read(path) -> (bool, str)``
- 也可注入 ``allowed_roots=[...]`` 做目录白名单
- 未注入时只允许当前工作目录子树（安全默认）

本模块不依赖任何工具域或模型层。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple

_HOST_CTX: Dict[str, Any] = {}


def configure_fs_policy(data: dict = None) -> None:
    """装配期注入文件策略。纯副作用，不返回信封。

    入参:
        check_write(callable, 可选)  check_write(path) -> (bool, str)
        check_read(callable, 可选)   check_read(path)  -> (bool, str)
        allowed_roots(list[str], 可选) 允许读写的目录白名单（绝对路径）
    """
    if data is None:
        return
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典对象")
    for key in ("check_write", "check_read"):
        cb = data.get(key)
        if cb is not None:
            if not callable(cb):
                raise ValueError(f"{key} 必须可调用，收到 {type(cb).__name__}")
            _HOST_CTX[key] = cb
    roots = data.get("allowed_roots")
    if roots is not None:
        if not isinstance(roots, (list, tuple)):
            raise ValueError("allowed_roots 必须是目录列表")
        _HOST_CTX["allowed_roots"] = [
            os.path.abspath(str(r)) for r in roots if str(r).strip()
        ]


def _to_bool_tuple(result: Any) -> Tuple[bool, str]:
    """把平台回调返回值归一成 (bool, reason)，兼容信封写法。"""
    if isinstance(result, dict) and "data" in result:
        d = result.get("data") or {}
        if isinstance(d, dict) and "allowed" in d:
            return bool(d["allowed"]), str(d.get("reason") or result.get("message") or "")
        return bool(result.get("code") == 200), str(result.get("message") or "")
    if isinstance(result, (tuple, list)) and result:
        return bool(result[0]), str(result[1] if len(result) > 1 else "")
    return bool(result), ""


def _inside(path: str, root: str) -> bool:
    try:
        p = os.path.realpath(path)
        r = os.path.realpath(root)
        return p == r or p.startswith(r + os.sep)
    except OSError:
        return False


def _check_path(path: Any, kind: str) -> Tuple[bool, str]:
    if path is None or not str(path).strip():
        return False, f"缺少 {kind} 路径"
    if not isinstance(path, str):
        return False, f"路径必须是字符串，收到 {type(path).__name__}"
    if not os.path.isabs(path):
        return False, "路径必须是绝对路径"
    if ".." in path.replace("\\", "/").split("/"):
        return False, "路径不允许包含 .."

    cb = _HOST_CTX.get(f"check_{kind}")
    if cb is not None:
        try:
            return _to_bool_tuple(cb(path))
        except Exception as e:
            return False, f"check_{kind} 回调抛异常：{type(e).__name__}: {e}"

    roots = _HOST_CTX.get("allowed_roots")
    if not roots:
        roots = [os.getcwd()]
    if any(_inside(path, root) for root in roots):
        return True, ""
    return False, f"超出可{('写入' if kind == 'write' else '读取')}范围"


def check_write_path(path: Any) -> Tuple[bool, str]:
    return _check_path(path, "write")


def check_read_path(path: Any) -> Tuple[bool, str]:
    return _check_path(path, "read")


__all__ = [
    "configure_fs_policy",
    "check_write_path",
    "check_read_path",
]
