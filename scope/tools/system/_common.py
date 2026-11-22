
"""
subprocess 可选参数归一化：timeout/shell/capture_output/text/encoding/errors。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。
布尔项容忍字符串写法（"true"/"1"/"yes"/"on" 与对应否定写法）。
"""

import os
from typing import Any, Dict


def _where(func_name: str) -> str:
    """错误位置标识，指向本文件_函数名。"""
    return f"{os.path.abspath(__file__)}_{func_name}"


def _ok(data=None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, func_name: str = "", code: int = 400, prefix: bool | None = None) -> Dict[str, Any]:
    """错误信封。默认 400（参数/校验错误）带「错误：」前缀、500 不带，与原语义一致；
    prefix 可显式覆盖——路由类提示（「暂不支持的 function」）原实现无前缀，
    用 prefix=False 保持，避免跨域文案不一致。"""
    if prefix is None:
        prefix = code == 400
    return {"code": code, "data": _where(func_name),
            "message": (f"错误：{message}" if prefix else message)}


def get_common_args(data: dict = None) -> Dict[str, Any]:
    """读取 subprocess 可选参数（均带默认值防错）。

    入参 (data):
        data(dict, 必填)       业务参数字典，读取其中 timeout/shell/capture_output/
                               text/encoding/errors 六个字段
        func_name(str, 可选)   错误位置标识里的函数名，默认 "get_common_args"

    返回:
        {"code":200, "data":{"value": {"timeout": float, "shell": bool,
                                       "capture_output": bool, "text": bool,
                                       "encoding": str, "errors": str}},
         "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}

    字段行为（原语义，勿改）:
        timeout       缺省 30，必须 > 0；None/空串回落默认值；非数字 → 400
        shell         缺省 True
        capture_output 缺省 True
        text          缺省 True
        encoding      缺省 "utf-8"
        errors        缺省 "ignore"
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "get_common_args")
    biz = data.get("data")
    if biz is None:
        return _err("缺少 data 字段（业务参数字典）", "get_common_args")
    if not isinstance(biz, dict):
        return _err(f"data 必须是字典，收到 {type(biz).__name__}", "get_common_args")
    func_name = str(data.get("func_name") or "get_common_args").strip() or "get_common_args"

    raw_timeout = biz.get("timeout", 30)
    if raw_timeout in (None, ""):
        raw_timeout = 30
    if isinstance(raw_timeout, (dict, list, tuple, set)):
        return _err(f"timeout 必须是数字，收到 {type(raw_timeout).__name__}", func_name)
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return _err("timeout 必须是数字", func_name)
    if timeout <= 0:
        return _err("timeout 必须大于 0", func_name)

    def _bool(key: str, default: bool) -> Dict[str, Any]:
        val = biz.get(key, default)
        if isinstance(val, bool):
            return _ok({"value": val})
        if isinstance(val, str):
            s = val.strip().lower()
            if s in ("1", "true", "yes", "on", "y"):
                return _ok({"value": True})
            if s in ("0", "false", "no", "off", "n"):
                return _ok({"value": False})
        return _err(f"{key} 必须是布尔值（true/false）", func_name)

    common_args: Dict[str, Any] = {"timeout": timeout}
    for key, default in (("shell", True), ("capture_output", True), ("text", True)):
        r = _bool(key, default)
        if r.get("code") != 200:
            return r
        common_args[key] = r["data"]["value"]
    for key, default in (("encoding", "utf-8"), ("errors", "ignore")):
        val = biz.get(key, default)
        if isinstance(val, (dict, list, tuple, set)):
            return _err(f"{key} 必须是字符串，收到 {type(val).__name__}", func_name)
        common_args[key] = str(val or default)
    return _ok({"value": common_args})
