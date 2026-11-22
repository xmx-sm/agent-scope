
"""
mcp 工具入口（工具列表）与连接建立。

原 mcp_client.py 拆分而来：本文件暴露 async_mcp_tools（列出 MCP server 提供的工具），
配置加载与客户端构建在 _config.py，连接建立在 client.py。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封；
参数错误一律 if 判断后返回 code 400，不裸抛。

模块布局:
    main_mcp.py    本文件，async_mcp_tools 入口
    _config.py     mcp_servers.json 加载、server 配置解析、MCPClient 构建、信封辅助 _ok/_err
    client.py      async_mcp_client：按配置建立 MCP 连接
"""

from typing import Any, Dict

from ._config import _ok
from .client import async_mcp_client



async def async_mcp_tools(data: dict = None) -> Dict[str, Any]:
    """
    直接获取 MCPTool 列表（在 Toolkit 之外使用，像普通 ToolBase 一样直接调用）。

    参数: 同 async_mcp_client
    返回:
        {"code": 200, "data": [MCPTool, ...], "message": "..."}
        或 {"code": 400/500, "data": 文件位置, "message": "错误描述"}
    """
    if not isinstance(data, dict):
        return {"code": 400, "data": None, "message": "错误：data 必须是字典对象"}
    r = await async_mcp_client(data)
    if r.get("code") != 200:
        return r
    tools = []
    errors = []
    for client in r.get("data") or []:
        try:
            tools.extend(await client.list_tools())
        except Exception as e:
            errors.append(f"{client.name}: {e}")
    message = f"MCP 工具获取成功，共 {len(tools)} 个"
    if errors:
        message += f"；失败 {len(errors)} 个: {'; '.join(errors)}"
    return _ok(tools, message)



if __name__ == "__main__":
    import asyncio

    async def main():
        # 入参类型校验
        print("== 非字典入参（原先裸抛 AttributeError）==")
        for bad in (None, "notdict", 123, [1, 2]):
            print(f"  {repr(bad)[:12]:14}", await async_mcp_client(bad))
        print("== 未配置 ==")
        print(await async_mcp_client({}))
        print("== 格式错误 ==")
        print(await async_mcp_client({"mcp": "bad"}))
        print("== 配置段类型错误（原先静默跳过）==")
        print(await async_mcp_client({"mcpServers": {"x": "not-a-dict"}}))
        print("== stdio 缺 command ==")
        print(await async_mcp_client({"mcpServers": {"x": {"type": "stdio"}}}))
        print("== http 缺 url ==")
        print(await async_mcp_client({"mcpServers": {"x": {"type": "http"}}}))
        print("== 指定文件不存在 ==")
        print(await async_mcp_client({"mcp": {"path": "/tmp/nope.json"}}))
        print("== load_from_file 直接调用 ==")
        from ._config import load_from_file
        print(load_from_file({}))
        print(load_from_file({"path": "/etc/hostname"}))

    asyncio.run(main())
