
"""
async_mcp_client — 按 data 配置建立 MCP 客户端（stdio / http 两种传输）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封；
参数错误一律 if 判断后返回 code 400，不裸抛。
"""

from typing import Any, Dict

from ._config import _err, _ok, _where, build_client, resolve_mcp_servers



async def async_mcp_client(data: dict = None) -> Dict[str, Any]:
    """
    加载 MCP 客户端列表。支持 JSON 文件自加载与 data 传参。

    参数 (data 字典):
        data: {
            "mcp": True,                     # 从默认配置文件 mcp_servers.json 加载
            # 或 {"path": "/x.json"}         # 从指定 JSON 文件加载
            # 或 {"mcpServers": {...}}       # 直接传 MCP 配置
        }
        # 兼容: data["mcpServers"] = {...}（直接传配置）

    mcpServers 配置（key 为 server 名，工具名前缀 mcp__{name}__*）:
        {
            "filesystem": {                  # server 名
                "type": "stdio",             # stdio / http（自动识别：有 command→stdio，有 url→http）
                "command": "npx",            # stdio 必填
                "args": ["@playwright/mcp@latest"],  # 可选 命令参数
                "env": {},                   # 可选 环境变量
                "cwd": "/path",              # 可选 工作目录
                "is_stateful": true,         # 可选 默认 stdio=True
                "enable_tools": [...],       # 可选 只启用指定工具
                "disable_tools": [...],      # 可选 禁用指定工具
                "execution_timeout": 60,     # 可选 工具执行超时秒数
            },
            "weather": {                     # http 类
                "type": "http",
                "url": "https://api.weather.com/mcp",  # http 必填（/sse 结尾→sse，否则 streamable_http）
                "headers": {"Authorization": "Bearer xxx"},  # 可选
                "timeout": 30,               # 可选
                "is_stateful": true,         # 可选 默认 http=False（stateless）
            },
        }

    返回:
        {"code": 200, "data": [MCPClient, ...], "message": "..."}
        stateful 的 client 已 connect；connect 失败的 server 跳过并计入 message。
        用法：挂 Toolkit → Toolkit(mcps=clients)
             Toolkit 之外 → await client.list_tools() 得到 MCPTool 列表直接用
        或 {"code": 400, "data": 文件位置, "message": "错误描述"}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_mcp_client")
    r = resolve_mcp_servers(data)
    if r.get("code") != 200:
        return {"code": 400, "data": _where("async_mcp_client"),
                "message": r.get("message") or "错误：未配置 MCP"}
    servers = r["data"]["servers"]
    source = r["data"]["source"]

    clients = []
    errors = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            errors.append(f"{name}: 配置段必须是字典，收到 {type(cfg).__name__}")
            continue
        br = build_client({"name": name, "cfg": cfg})
        if br.get("code") != 200:
            errors.append(f"{name}: {str(br.get('message')).removeprefix('错误：')}")
            continue
        client = br["data"]["client"]
        if not client.is_stateful:
            clients.append(client)
            continue
        try:
            await client.connect()
            clients.append(client)
        except Exception as e:
            errors.append(f"{name}: {e}")

    message = f"MCP 客户端加载成功，共 {len(clients)} 个（来源: {source}）"
    if errors:
        message += f"；失败 {len(errors)} 个: {'; '.join(errors)}"
    return _ok(clients, message)
