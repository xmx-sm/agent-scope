

"""
net 工具统一入口与 function 路由。

原 async_req_tools.py 拆分而来：本文件只保留调度，各功能独立成模块。
新增功能：写一个 <function>.py，并在本文件路由里加一个 if function == "..." 分支。

模块布局:
    main_net.py       本文件，async_req_tools 入口与路由
    _client.py        共享 httpx 客户端单例与 timeout 归一化（有状态，故独立）
    weather.py        function="get_weather"      sojson 城市天气
    cityid.py         function="getcityid"        城市名 → 城市 ID
    weather_wttr.py   function="get_weather_wttr" wttr.in 天气
    http_request.py   function="http_request"     通用 HTTP 请求
    download.py       function="download"         文件下载
"""

from typing import Dict, Any

from .cityid import async_getcityid
from ._envelope import _err
from .download import async_req_download
from .http_request import async_http_request
from .weather import async_get_weather
from .weather_wttr import async_get_weather_wttr



async def async_req_tools(data: dict) -> Dict[str, Any]:
    """
    网络访问工具统一入口（异步）。data["function"] 决定执行哪个功能，其余字段为该功能的业务参数。

    参数 (data 字典):
        data: {"function": 要执行的功能名称, # 必填
               ...功能业务参数见下方各功能说明}

    支持的功能与业务参数:
        ① function="get_weather" — 根据城市 ID 获取实时天气和未来天预报
            业务参数: city_id(str, 必填) 城市数字 ID，如 "101030100" 表示天津
                     timeout(int/float, 可选) 请求超时秒数，默认 5
            返回: {"code":200, "data": 天气JSON, "message":"success"}
        ② function="getcityid" — 根据城市中文名称查询城市 ID（返回的 ID 可传给 get_weather）
            业务参数: city_name(str, 必填) 城市中文名称，如 "天津"、"北京"
                     timeout(int/float, 可选) 请求超时秒数，默认 5
            返回: {"code":200, "data": 城市信息JSON, "message":"success"}
        ③ function="get_weather_wttr" — 用 wttr.in 查询天气（支持中文/英文城市名，无需城市ID）
            业务参数: city(str, 必填) 城市名，如 "天津"、"Tianjin"、"北京"
                     format(str, 可选) 返回格式："j1" 完整JSON(默认) / "3" 简洁文本
                     timeout(int/float, 可选) 请求超时秒数，默认 5
            返回: {"code":200, "data": 天气数据, "message":"success"}
        ④ function="http_request" — 通用 HTTP 请求（动态传网页/接口地址、请求头、方法等）
            业务参数: url(str, 必填) 网页/接口地址
                     method(str, 可选) 默认 GET；GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS
                     headers(dict, 可选) 请求头，如 {"Authorization":"Bearer xxx","User-Agent":"..."}
                     params(dict, 可选) URL 查询参数
                     data(dict|str, 可选) 表单请求体（与 json 二选一）
                     json(dict, 可选) JSON 请求体（与 data 二选一）
                     timeout(int/float, 可选) 默认 10
                     response_type(str, 可选) "auto"(默认)/"json"/"text"
                     max_length(int, 可选) 返回内容最大字符数，默认 10000；<=0 不截断
                     verify(bool, 可选) 是否校验 SSL 证书，默认 True
            返回: {"code":200, "data": {status_code, reason, headers, content, json(可解析), truncated}, "message":"success"}
        ⑤ function="download" — 流式下载文件到本地（适合大文件，实时汇报下载进度）
            业务参数: url(str, 必填) 下载地址
                     save_path(str, 必填) 本地保存路径（绝对路径，父目录不存在时自动创建）
                     timeout(int/float, 可选) 请求/读取超时秒数，默认 30
                     max_size(int, 可选) 最大下载字节数（超出即停止），默认 0 不限制
                     report_every(int, 可选) 每下载多少字节汇报一次进度，默认 1048576(1MB)
            返回（流式）: 边下载边产出进度文本（如 "已下载 5MB"）；
                         最后产出 {"code":200, "data": {save_path, size, status_code}, "message":"下载完成"}

    调用示例:
        async_req_tools({"function":"get_weather", "city_id":"101030100"})
        async_req_tools({"function":"getcityid", "city_name":"天津"})
        async_req_tools({"function":"get_weather_wttr", "city":"天津"})
        async_req_tools({"function":"get_weather_wttr", "city":"Tianjin", "format":"3"})
        async_req_tools({"function":"http_request", "url":"https://example.com",
                   "headers":{"User-Agent":"Mozilla/5.0"}})
        async_req_tools({"function":"http_request", "url":"https://httpbin.org/post",
                   "method":"POST", "json":{"a":1}, "response_type":"json"})
        async_req_tools({"function":"download", "url":"https://example.com/file.zip",
                   "save_path":"/root/git_app/downloads/file.zip"})

    返回:
        {"code": 200, "data": ..., "message": "success"}
        或 {"code": 400/500, "data": 文件位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_req_tools")
    raw_fn = data.get("function", "")
    if isinstance(raw_fn, (dict, list, tuple, set)):
        return _err(f"function 必须是字符串，收到 {type(raw_fn).__name__}", "async_req_tools")
    function = str(raw_fn or "").strip()
    if not function:
        return _err("data 中缺少 function 字段", "async_req_tools")
    if function == "get_weather":
        return await async_get_weather(data)
    if function == "getcityid":
        return await async_getcityid(data)
    if function == "get_weather_wttr":
        return await async_get_weather_wttr(data)
    if function == "http_request":
        return await async_http_request(data)
    if function == "download":
        return await async_req_download(data)
    return _err(f"暂不支持的 function: {function}，"
                f"支持: get_weather / getcityid / get_weather_wttr / http_request / download",
                "async_req_tools", prefix=False)



if __name__ == "__main__":
    # 网络访问工具测试：getcityid → get_weather
    import asyncio

    async def main():
        print("== getcityid ==")
        print(await async_req_tools({"function": "getcityid", "city_name": "天津"}))
        print("== get_weather ==")
        print(await async_req_tools({"function": "get_weather", "city_id": "101030100"}))
        print("== get_weather_wttr(简洁) ==")
        print(await async_req_tools({"function": "get_weather_wttr", "city": "Tianjin", "format": "3"}))
        print("== get_weather_wttr(JSON) ==")
        r = await async_req_tools({"function": "get_weather_wttr", "city": "北京"})
        print(r["code"], list(r["data"].keys()) if r["code"] == 200 else r["message"])
        print("== http_request(GET) ==")
        print(await async_req_tools({"function": "http_request", "url": "https://example.com", "max_length": 200}))
        print("== http_request(POST json) ==")
        r = await async_req_tools({"function": "http_request", "url": "https://httpbin.org/post", "method": "POST", "json": {"a": 1}, "response_type": "json", "max_length": 200})
        print(r["code"], list(r["data"].keys()) if r["code"] == 200 else r["message"])
        print("== download(流式) ==")
        async for item in await async_req_tools({"function": "download", "url": "https://example.com", "save_path": "/tmp/example_dl.html"}):
            print("  ", item)
        print("== 参数校验 ==")
        print(await async_req_tools({"function": "get_weather"}))
        print(await async_req_tools({"function": "get_weather_wttr"}))
        print(await async_req_tools({"function": "http_request"}))
        print(await async_req_tools({"function": "http_request", "url": "x", "method": "FETCH"}))
        print(await async_req_tools({"function": "bad"}))

    asyncio.run(main())
