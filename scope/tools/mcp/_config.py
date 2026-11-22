
"""
MCP 配置加载与客户端构建。

DEFAULT_MCP_CONFIG 指向本目录下的 mcp_servers.json；
工具名前缀约定为 mcp__{name}__*，由 build_client 产出。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封；
参数错误一律 if 判断后返回 code 400，不裸抛。
"""


import json
import os
from typing import Any, Dict

from agentscope.mcp import MCPClient, StdioMCPConfig, HttpMCPConfig

from config import get as _cfg_get


DEFAULT_MCP_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_servers.json")


def _where(func_name: str) -> str:
    """错误位置标识，指向本文件_函数名。"""
    return f"{os.path.abspath(__file__)}_{func_name}"


def _ok(data=None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, func_name: str = "") -> Dict[str, Any]:
    return {"code": 400, "data": _where(func_name), "message": f"错误：{message}"}


def load_from_file(data: dict = None) -> Dict[str, Any]:
    """读取 JSON 配置文件，取出 mcpServers / servers 段。

    入参 (data):
        path(str, 必填)  JSON 配置文件路径

    返回:
        {"code":200, "data":{"servers": dict}, "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}

    读文件/解析失败返回 400 而非抛异常——配置文件路径来自调用方，属可预期错误。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "load_from_file")
    path = data.get("path")
    if path is None or not str(path).strip():
        return _err("缺少 path 字段（JSON 配置文件路径）", "load_from_file")
    if isinstance(path, (dict, list, tuple, set)):
        return _err(f"path 必须是字符串，收到 {type(path).__name__}", "load_from_file")
    p = str(path).strip()
    if not os.path.exists(p):
        return _err(f"配置文件不存在: {p}", "load_from_file")
    if not os.path.isfile(p):
        return _err(f"配置路径不是文件: {p}", "load_from_file")
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        return _err(f"配置文件 JSON 解析失败: {p}（{e}）", "load_from_file")
    except OSError as e:
        return _err(f"配置文件读取失败: {p}（{e}）", "load_from_file")
    if isinstance(cfg, dict):
        for key in ("mcpServers", "servers"):
            if key in cfg and isinstance(cfg[key], dict):
                return _ok({"servers": dict(cfg[key])})
        return _ok({"servers": cfg})
    return _ok({"servers": {}})


def resolve_mcp_servers(data: dict = None) -> Dict[str, Any]:
    """解析 MCP 配置来源。

    入参 (data):
        mcp(dict|bool, 可选)      True=读默认配置；{"path":...}=读指定文件；
                                  {"mcpServers":{...}}=直接传配置
        mcpServers(dict, 可选)    兼容写法，直接传配置

    返回:
        {"code":200, "data":{"servers": dict, "source": str}, "message":"success"}
        {"code":400, "data": 位置, "message": 未配置/格式错误原因}

    注意 source 与 servers 的三种组合（原语义，勿混）:
        code 400 + message       → 未配置或格式错误，调用方应中止
        code 200 + servers={}    → 视为未配置任何 MCP，不阻断工具加载
        code 200 + servers 非空  → 正常
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "resolve_mcp_servers")
    mcp_cfg = data.get("mcp")
    if mcp_cfg is None:
        mcp_cfg = data.get("mcpServers")
    if mcp_cfg in (None, False, ""):
        return _err("未配置 MCP", "resolve_mcp_servers")
    if mcp_cfg is True:
        # 缺省配置文件路径：sqlite 默认 > 本目录常量兜底（部署方可把路径指到
        # /etc/agent/mcp.json 等，免改源码）。取不到回落 DEFAULT_MCP_CONFIG。
        default_path = _cfg_get("mcp.config_path", DEFAULT_MCP_CONFIG) or DEFAULT_MCP_CONFIG
        if not os.path.exists(default_path):
            # 默认配置文件不存在视为"未配置任何 MCP"，不阻断工具加载
            return _ok({"servers": {}, "source": "默认配置文件不存在（视为未配置 MCP）"})
        r = load_from_file({"path": default_path})
        if r.get("code") != 200:
            return _err(str(r.get("message")).removeprefix("错误："), "resolve_mcp_servers")
        return _ok({"servers": r["data"]["servers"], "source": "默认配置文件"})
    if isinstance(mcp_cfg, dict):
        if "path" in mcp_cfg:
            p = str(mcp_cfg["path"])
            if not os.path.exists(p):
                return _err(f"指定配置文件不存在: {p}", "resolve_mcp_servers")
            r = load_from_file({"path": p})
            if r.get("code") != 200:
                return _err(str(r.get("message")).removeprefix("错误："), "resolve_mcp_servers")
            return _ok({"servers": r["data"]["servers"], "source": "指定配置文件"})
        for key in ("mcpServers", "servers"):
            if key in mcp_cfg and isinstance(mcp_cfg[key], dict):
                return _ok({"servers": dict(mcp_cfg[key]), "source": f"data[{key}]"})
        return _ok({"servers": dict(mcp_cfg), "source": "data[mcp]"})
    return _err(f"mcp 配置格式错误（收到 {type(mcp_cfg).__name__}，期望 dict 或 True）",
                "resolve_mcp_servers")


def build_client(data: dict = None) -> Dict[str, Any]:
    """根据单个 server 配置构建 MCPClient。

    入参 (data):
        name(str, 必填)   server 名
        cfg(dict, 必填)   该 server 的配置段，字段见 async_mcp_client 文档

    返回:
        {"code":200, "data":{"client": MCPClient, "transport": str, "is_stateful": bool},
         "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}

    传输判断：type 优先（stdio/cmd → stdio；http → http）；
    未写 type 时：有 command 且无 url → stdio，有 url → http。
    is_stateful 默认：stdio=True（必须），http=False。

    MCPClient 实例放在 data.client —— 它是活对象，不可 JSON 序列化；
    调用方取出后直接用于 Toolkit(mcps=[...]) 或 await client.list_tools()。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "build_client")
    name = data.get("name")
    if name is None or not str(name).strip():
        return _err("缺少 name 字段（server 名）", "build_client")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段（该 server 的配置段）", "build_client")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "build_client")

    t = str(cfg.get("type", "") or "").strip().lower()
    has_command = bool(cfg.get("command"))
    has_url = bool(cfg.get("url"))
    is_stdio = t in ("stdio", "cmd") or (not t and has_command and not has_url)
    is_stateful = cfg.get("is_stateful")

    if is_stdio:
        if is_stateful is None:
            is_stateful = True
        command = cfg.get("command")
        if not command or not str(command).strip():
            return _err(f"stdio 传输缺少 command（server: {name}）", "build_client")
        mcp_config = StdioMCPConfig(
            command=str(command),
            args=cfg.get("args"),
            env=cfg.get("env"),
            cwd=cfg.get("cwd"),
        )
    else:
        if is_stateful is None:
            is_stateful = False
        url = cfg.get("url")
        if not url or not str(url).strip():
            return _err(f"http 传输缺少 url（server: {name}）", "build_client")
        mcp_config = HttpMCPConfig(
            url=str(url),
            headers=cfg.get("headers"),
            timeout=cfg.get("timeout"),
        )
    try:
        client = MCPClient(
            name=str(name),
            is_stateful=bool(is_stateful),
            mcp_config=mcp_config,
            enable_tools=cfg.get("enable_tools"),
            disable_tools=cfg.get("disable_tools"),
            execution_timeout=cfg.get("execution_timeout"),
        )
    except Exception as e:
        return _err(f"构建 MCPClient 失败（server: {name}）：{type(e).__name__}: {e}", "build_client")
    return _ok({"client": client, "transport": "stdio" if is_stdio else "http",
                "is_stateful": bool(is_stateful)})
