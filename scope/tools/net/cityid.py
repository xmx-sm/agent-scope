

"""
function="getcityid" — 城市名解析为城市数字 ID（供 get_weather 使用）。
"""

from typing import Dict, Any

from ._client import get_http_client, get_timeout
from ._envelope import _err, _ok



async def async_getcityid(data: dict) -> Dict[str, Any]:
    """
    根据城市中文名称查询对应的城市 ID。

    调用 songzixian 城市编码 API。返回的 ID 可传递给 get_weather 使用。

    参数 (data 字典):
        data: {city_name: 城市中文名称，如 "天津"、"北京",
               timeout: 请求超时秒数(可选,默认5)}

    返回:
        {"code": 200, "data": 城市信息JSON, "message": "success"}
        或 {"code": 400/500, "data": 文件位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "getcityid")
    city_name = str(data.get("city_name", "") or "").strip()
    if not city_name:
        return _err("data 中缺少 city_name 字段", "getcityid")
    timeout_r = get_timeout({"data": data, "func_name": "getcityid"})
    if timeout_r.get("code") != 200:
        return timeout_r
    # url: str — songzixian 城市编码 API 地址，city_name 作为查询参数
    url = f"https://api.songzixian.com/api/china-city?dataSource=LOCAL_CHINA_CITY&district={city_name}"
    try:
        # resp: httpx.Response — 城市编码查询的 HTTP 响应（异步 I/O）
        resp = await get_http_client()["data"].get(url, timeout=timeout_r["data"]["value"])
        resp.raise_for_status()
        return _ok(resp.json(), "success")
    except Exception as e:
        return _err(f"处理失败，原因：{e}", "getcityid", code=500)
