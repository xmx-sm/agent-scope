
"""
net 工具共享辅助：进程级 httpx 客户端单例与 timeout 参数归一化。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

两个单例 _HTTP_CLIENT / _HTTP_CLIENT_INSECURE 必须与本文件同模块
（依赖 global 语义），勿外移。

信封机器（_where/_ok/_err）已上提到 _envelope.py —— 本模块只是使用者。
⚠️ 因此本模块错误位置标识的文件部分是 `_envelope.py`，函数名部分才是实际出处
   （如 `_envelope.py_get_timeout`）。与 db 域的 `_helper.py_<fn>` 同形，
   定位价值在函数名层面，见 docs/踩坑记录.md A15。
"""


import httpx
from typing import Any, Dict

from ._envelope import _err, _ok


# 共享异步 HTTP 客户端：进程内复用同一连接池，避免每请求新建 client 的连接建立/关闭开销，
# 高并发下大幅降低延迟与事件循环阻塞。timeout 通过每请求参数覆盖。
#
# verify=False 走独立单例 _HTTP_CLIENT_INSECURE。原件在此处每次新建 AsyncClient 且
# 无任何 aclose()，实测 5 次调用泄漏 5 个未关闭实例（连接池永不释放）；
# 改为第二个单例后既复用连接池又不泄漏，行为对调用方透明。
_HTTP_CLIENT = None
_HTTP_CLIENT_INSECURE = None

_HTTP_CLIENT_LIMITS = httpx.Limits(max_connections=1000, max_keepalive_connections=200)
_HTTP_CLIENT_TIMEOUT = 30


def get_http_client(data: dict = None) -> Dict[str, Any]:
    """获取共享 AsyncClient（懒创建，进程生命周期内复用）。

    入参 (data):
        verify(bool, 可选, 默认 True)  是否校验 TLS 证书。
                                      True  → 共享实例 _HTTP_CLIENT
                                      False → 共享实例 _HTTP_CLIENT_INSECURE（与校验实例隔离，
                                              避免禁用校验的调用污染默认连接池）
        timeout(float, 可选)           仅用于新建实例时的默认超时；已有实例不因此改变
                                       （每请求超时请用 request 的 timeout 参数）

    返回:
        {"code":200, "data": AsyncClient, "message":"success"}
        data 直接是 httpx.AsyncClient 活对象（不可 JSON 序列化），
        调用方取出后直接 .get()/.request()/.stream()。
        或 {"code":400, "data": 位置, "message": 错误描述}

    ⚠️ 返回的是**共享**实例，调用方不得 aclose()——会连带影响后续所有请求。
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "get_http_client")
    raw_verify = data.get("verify", True)
    if raw_verify in (None, ""):
        raw_verify = True
    if not isinstance(raw_verify, bool):
        if isinstance(raw_verify, str):
            s = raw_verify.strip().lower()
            if s in ("1", "true", "yes", "on", "y"):
                raw_verify = True
            elif s in ("0", "false", "no", "off", "n"):
                raw_verify = False
            else:
                return _err(f"verify 必须是布尔值，收到字符串 {raw_verify!r}", "get_http_client")
        else:
            return _err(f"verify 必须是布尔值，收到 {type(raw_verify).__name__}", "get_http_client")
    raw_timeout = data.get("timeout")
    timeout = _HTTP_CLIENT_TIMEOUT
    if raw_timeout not in (None, ""):
        if isinstance(raw_timeout, (dict, list, tuple, set)):
            return _err(f"timeout 必须是数字，收到 {type(raw_timeout).__name__}", "get_http_client")
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            return _err("timeout 必须是数字", "get_http_client")
        if timeout <= 0:
            return _err("timeout 必须大于 0", "get_http_client")

    global _HTTP_CLIENT, _HTTP_CLIENT_INSECURE
    slot = _HTTP_CLIENT if raw_verify else _HTTP_CLIENT_INSECURE
    if slot is None or slot.is_closed:
        slot = httpx.AsyncClient(timeout=timeout, verify=raw_verify, limits=_HTTP_CLIENT_LIMITS)
        if raw_verify:
            _HTTP_CLIENT = slot
        else:
            _HTTP_CLIENT_INSECURE = slot
    return _ok(slot)


def get_timeout(data: dict = None) -> Dict[str, Any]:
    """读取可选 timeout 参数（int/float，须 >0）。

    入参 (data):
        data(dict, 必填)       业务参数字典，读取其中 timeout 字段
        func_name(str, 可选)   错误位置标识里的函数名，默认 "get_timeout"
        default(float, 可选)   缺省超时秒数，默认 5

    返回:
        {"code":200, "data":{"value": float}, "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "get_timeout")
    biz = data.get("data")
    if biz is None:
        return _err("缺少 data 字段（业务参数字典）", "get_timeout")
    if not isinstance(biz, dict):
        return _err(f"data 必须是字典，收到 {type(biz).__name__}", "get_timeout")
    func_name = str(data.get("func_name") or "get_timeout").strip() or "get_timeout"
    raw_default = data.get("default", 5)
    if raw_default in (None, ""):
        raw_default = 5
    if isinstance(raw_default, (dict, list, tuple, set)):
        return _err(f"default 必须是数字，收到 {type(raw_default).__name__}", func_name)
    try:
        default = float(raw_default)
    except (TypeError, ValueError):
        return _err("default 必须是数字", func_name)

    if "timeout" not in biz or biz["timeout"] is None or biz["timeout"] == "":
        return _ok({"value": default})
    raw = biz["timeout"]
    if isinstance(raw, (dict, list, tuple, set)):
        return _err(f"timeout 必须是数字，收到 {type(raw).__name__}", func_name)
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return _err("timeout 必须是数字", func_name)
    if val <= 0:
        return _err("timeout 必须大于 0", func_name)
    return _ok({"value": val})
