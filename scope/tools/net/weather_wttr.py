

"""
function="get_weather_wttr" — wttr.in 天气查询。
"""

from typing import Dict, Any

from ._client import get_http_client, get_timeout
from ._envelope import _err, _ok



async def async_get_weather_wttr(data: dict) -> Dict[str, Any]:
    """
    用 wttr.in 查询天气（支持中文/英文城市名，无需城市 ID，免 key）。

    参数 (data 字典):
        data: {city: 城市名(必填)，如 "天津"、"Tianjin"、"北京",
               format: 返回格式(可选)，"j1" 完整JSON(默认) / "3" 简洁文本，
               timeout: 请求超时秒数(可选,默认5)}

    返回:
        {"code": 200, "data": 天气数据, "message": "success"}
        或 {"code": 400/500, "data": 文件位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "get_weather_wttr")
    city = str(data.get("city", "") or "").strip()
    if not city:
        return _err("data 中缺少 city 字段", "get_weather_wttr")
    fmt = str(data.get("format", "j1") or "j1").strip()
    if fmt not in ("j1", "3"):
        return _err("format 仅支持 j1(JSON) 或 3(简洁文本)", "get_weather_wttr")
    timeout_r = get_timeout({"data": data, "func_name": "get_weather_wttr"})
    if timeout_r.get("code") != 200:
        return timeout_r
    # url: str — wttr.in 天气 API，city 拼接在路径中（requests 自动 URL 编码中文）
    url = f"https://wttr.in/{city}?format={fmt}"
    try:
        # resp: httpx.Response — wttr.in 返回的 HTTP 响应（异步 I/O）
        resp = await get_http_client()["data"].get(url, timeout=timeout_r["data"]["value"])
        resp.raise_for_status()
        if fmt == "j1":
            return _ok(resp.json(), "success")
        return _ok(resp.text.strip(), "success")
    except Exception as e:
        return _err(f"处理失败，原因：{e}", "get_weather_wttr", code=500)
