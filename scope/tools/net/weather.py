

"""
function="get_weather" — sojson 免费城市天气查询。
"""

from typing import Dict, Any

from ._client import get_http_client, get_timeout
from ._envelope import _err, _ok



async def async_get_weather(data: dict) -> Dict[str, Any]:
    """
    根据城市 ID 获取实时天气和未来天预报。

    城市 ID 可通过 getcityid 工具查询获取。

    参数 (data 字典):
        data: {city_id: 城市数字 ID，如 "101030100" 表示天津,
               timeout: 请求超时秒数(可选,默认5)}

    返回:
        {"code": 200, "data": 天气JSON, "message": "success"}
        或 {"code": 400/500, "data": 文件位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "get_weather")
    city_id = str(data.get("city_id", "") or "").strip()
    if not city_id:
        return _err("data 中缺少 city_id 字段", "get_weather")
    timeout_r = get_timeout({"data": data, "func_name": "get_weather"})
    if timeout_r.get("code") != 200:
        return timeout_r
    # url: str — sojson 免费天气 API 地址，city_id 拼接在路径中
    url = f"http://t.weather.sojson.com/api/weather/city/{city_id}"
    try:
        # resp: httpx.Response — API 返回的原始 HTTP 响应（异步 I/O，不占线程）
        resp = await get_http_client()["data"].get(url, timeout=timeout_r["data"]["value"])
        resp.raise_for_status()
        return _ok(resp.json(), "success")
    except Exception as e:
        return _err(f"处理失败，原因：{e}", "get_weather", code=500)
