

"""
function="http_request" — 通用 HTTP 请求（方法/头/体/超时可控）。
"""


import httpx
from typing import Dict, Any

from ._client import get_http_client, get_timeout
from config import get as _c, pick_str as _ps
from common.net_guard import check_url as _check_url
from ._envelope import _err, _ok



async def async_http_request(data: dict) -> Dict[str, Any]:
    """
    通用 HTTP 请求工具：动态传入网页/接口地址、请求头、方法、查询/请求体等。

    参数 (data 字典):
        data: {"url": 网页/接口地址(必填)，
               "method": 请求方法(可选,默认 GET；GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS)，
               "headers": 请求头 dict(可选)，
               "params": URL 查询参数 dict(可选)，
               "data": 表单请求体 dict 或 str(可选，POST 等)，
               "json": JSON 请求体 dict(可选，POST 等，与 data 二选一)，
               "timeout": 请求超时秒数(可选,默认10)，
               "response_type": "auto"(默认)/"json"/"text"，
               "max_length": 返回内容最大字符数(可选,默认10000,<=0 不截断)，
               "verify": 是否校验 SSL 证书(可选,默认 True)}

    返回:
        {"code":200,"data":{"status_code","reason","headers","content"(可能截断),"json"(可解析时),"truncated"},
         "message":"success"}
        或 {"code":400/500,"data":文件位置,"message":"错误描述"}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "http_request")
    url = str(data.get("url", "") or "").strip()
    if not url:
        return _err("data 中缺少 url 字段", "http_request")
    allowed, reason = await _check_url(url)
    if not allowed:
        return _err(f"URL 被拒绝：{reason}", "http_request")
    method = _ps(data.get("method"), "net.http_request.method", "GET").strip().upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
        return _err(f"错误：暂不支持的 method: {method}", "http_request")
    headers = data.get("headers")
    if headers is not None and not isinstance(headers, dict):
        return _err("headers 必须是字典", "http_request")
    params = data.get("params")
    if params is not None and not isinstance(params, dict):
        return _err("params 必须是字典", "http_request")
    body = data.get("data")
    json_body = data.get("json")
    if body is not None and json_body is not None:
        return _err("data 与 json 不能同时提供", "http_request")
    timeout_r = get_timeout({"data": data, "func_name": "http_request",
                             "default": _c("net.http_request.timeout", 10)})
    if timeout_r.get("code") != 200:
        return timeout_r
    try:
        max_length = int(data.get("max_length") or _c("net.http_request.max_length", 10000))
    except (TypeError, ValueError):
        return _err("max_length 必须是整数", "http_request")
    response_type = str(data.get("response_type") or _c("net.http_request.response_type", "auto")).strip().lower()
    if response_type not in ("auto", "json", "text"):
        return _err("response_type 仅支持 auto/json/text", "http_request")
    # verify 交由 get_http_client 统一判定：无法识别的值报 400，不再静默降级为禁用 TLS 校验
    cr = get_http_client({"verify": data.get("verify")})   # 传 None 让 _pick 读 sqlite net.verify
    if cr.get("code") != 200:
        return cr
    client = cr["data"]
    try:
        # resp: httpx.Response — 通用 HTTP 请求（异步 I/O，不占线程）
        resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=body,
                json=json_body,
                timeout=timeout_r["data"]["value"],
            )
        resp.raise_for_status()
        content = resp.text
        truncated = False
        if max_length > 0 and len(content) > max_length:
            content = content[:max_length]
            truncated = True
        result = {
            "status_code": resp.status_code,
            "reason": resp.reason_phrase,
            "headers": dict(resp.headers),
            "content": content,
            "truncated": truncated,
        }
        if response_type in ("json", "auto"):
            try:
                result["json"] = resp.json()
            except Exception:
                if response_type == "json":
                    return _err("响应不是合法 JSON", "http_request", code=500)
        return _ok(result, "success")
    except httpx.TimeoutException:
        return _err(f"请求超时：{url}", "http_request", code=500)
    except httpx.HTTPStatusError as e:
        return _err(f"HTTP错误：{e}", "http_request", code=500)
    except Exception as e:
        return _err(f"请求失败：{e}", "http_request", code=500)
