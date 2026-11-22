

"""
文件读写闸门：_HOST_CTX / configure_fs_policy / _to_bool_tuple / _check_write / _check_read。

**net 域共用层**——合并前只有 crawl 的 screenshot/extract_pdf 过闸门，
`net/download.py` 的 save_path 是直接 open 落盘、不过闸门的（同一域内两种命运）。
合并后 download 也走这里，不对称消除。

_HOST_CTX 是模块级可变全局，由 configure_fs_policy() 在装配时写入，
_check_write/_check_read 读取，三者必须同模块（拆开会破坏可变状态语义）。

⚠️ 外部契约未变：平台注入的回调仍是 `check_write(path) -> (bool, str)` 元组。
   _to_bool_tuple 在内部把元组转成信封，同时兼容回调直接返回信封的写法，
   **平台侧无需改注入代码**。

⚠️ 未注入时闸门放行（高代码单机场景）——线上必须注入，否则可写读任意路径。
"""


import os
from typing import Any, Dict

from ._envelope import _err, _ok

# 宿主平台注入（configure_fs_policy）
_HOST_CTX: Dict[str, Any] = {}


def configure_fs_policy(data: dict = None) -> None:
    """平台装配时注入文件闸门与 headed 许可。**纯副作用，不套信封**。

    入参 (data):
        check_write(callable, 可选)  check_write(path) -> (bool, str)
        check_read(callable, 可选)   check_read(path)  -> (bool, str)
        allow_headed(bool, 可选)     是否允许有头浏览器

    ⚠️ 平台侧必须注入，否则闸门放行（高代码单机场景）。
    注入的回调**仍返回 (bool, str) 元组**——外部契约未变，本层内部转信封。
    """
    if data is None:
        return
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典对象")
    cw = data.get("check_write")
    if cw is not None:
        if not callable(cw):
            raise ValueError(f"check_write 必须可调用，收到 {type(cw).__name__}")
        _HOST_CTX["check_write"] = cw
    cr = data.get("check_read")
    if cr is not None:
        if not callable(cr):
            raise ValueError(f"check_read 必须可调用，收到 {type(cr).__name__}")
        _HOST_CTX["check_read"] = cr
    _HOST_CTX["allow_headed"] = bool(data.get("allow_headed", False))


def _to_bool_tuple(result: Any) -> tuple:
    """把平台回调的返回值归一成 (bool, str)。

    平台契约是 (bool, str)；若回调返回信封（本层风格）也兼容解开。
    """
    if isinstance(result, dict) and "data" in result:
        d = result.get("data") or {}
        if isinstance(d, dict) and "allowed" in d:
            return bool(d["allowed"]), str(d.get("reason") or result.get("message") or "")
        return bool(result.get("code") == 200), str(result.get("message") or "")
    if isinstance(result, (tuple, list)) and result:
        return bool(result[0]), str(result[1] if len(result) > 1 else "")
    return bool(result), ""


def _check_write(data: dict = None) -> Dict[str, Any]:
    """写入闸门判定。

    入参 (data): path(str, 必填)
    返回: {"code":200, "data":{"allowed": bool, "reason": str}, "message":"success"}
          或 {"code":400, "data": 位置, "message": "错误：<原因>"}

    平台注入了 check_write 时以其判定为准（回调契约仍是 (bool, str)，本层转信封）；
    未注入时走独立模式兜底闸门：仅允许当前工作目录子树。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_check_write")
    path = data.get("path")
    if path is None or not str(path).strip():
        return _err("缺少 path 字段", "_check_write")
    if isinstance(path, (dict, list, tuple, set)):
        return _err(f"path 必须是字符串，收到 {type(path).__name__}", "_check_write")
    cw = _HOST_CTX.get("check_write")
    if cw is not None:
        try:
            allowed, reason = _to_bool_tuple(cw(str(path)))
        except Exception as e:
            return _err(f"check_write 回调抛异常：{type(e).__name__}: {e}", "_check_write")
        return _ok({"allowed": allowed, "reason": reason})
    ap = os.path.abspath(str(path))
    if ap == os.getcwd() or ap.startswith(os.getcwd() + os.sep):
        return _ok({"allowed": True, "reason": ""})
    return _ok({"allowed": False,
                "reason": "超出可写入范围（scope 独立模式仅允许当前工作目录子树）"})


def _check_read(data: dict = None) -> Dict[str, Any]:
    """读取闸门判定。入参/返回同 _check_write。

    平台注入了 check_read 时以其判定为准；未注入时走独立模式兜底闸门。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_check_read")
    path = data.get("path")
    if path is None or not str(path).strip():
        return _err("缺少 path 字段", "_check_read")
    if isinstance(path, (dict, list, tuple, set)):
        return _err(f"path 必须是字符串，收到 {type(path).__name__}", "_check_read")
    cr = _HOST_CTX.get("check_read")
    if cr is not None:
        try:
            allowed, reason = _to_bool_tuple(cr(str(path)))
        except Exception as e:
            return _err(f"check_read 回调抛异常：{type(e).__name__}: {e}", "_check_read")
        return _ok({"allowed": allowed, "reason": reason})
    ap = os.path.abspath(str(path))
    if ap == os.getcwd() or ap.startswith(os.getcwd() + os.sep):
        return _ok({"allowed": True, "reason": ""})
    return _ok({"allowed": False,
                "reason": "超出可读取范围（scope 独立模式仅允许当前工作目录子树）"})
