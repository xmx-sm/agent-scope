"""按 AI 工具权限构建 AgentScope Toolkit。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from agentscope.tool import (
    Edit,
    FunctionTool,
    Glob,
    Grep,
    LocalBackend,
    Read,
    TaskCreate,
    TaskGet,
    TaskList,
    TaskUpdate,
    ToolGroup,
    Toolkit,
    Write,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.agent import rag as rag_service
from app.services.agent.scope_bridge import user_workspace
from app.services.config.service import async_get_config
from app.services.security.db_policy import (
    apply_db_policy,
    async_get_db_policy,
    sanitize_model_db_config,
)
from app.services.security.identity import merge_identity
from app.services.tools.evaluate import async_tool_view
from app.services.tools.tool_config import async_effective as async_tool_config


def _scope_tool(fn: Callable[..., Awaitable[Any]], name: str, description: str,
                user_id: str) -> FunctionTool:
    async def call(**kwargs):
        return await fn(merge_identity({"user_id": user_id, "_actor_kind": "ai"}, kwargs))

    schema = {
        "type": "object",
        "properties": {
            "function": {"type": "string", "description": "功能名"},
            "args": {"type": "object", "description": "功能参数"},
        },
        "additionalProperties": True,
    }
    return FunctionTool(
        call,
        name=name,
        description=f"{description}\n必须传 function 字段；其他参数平铺在顶层。",
        input_schema=schema,
        is_concurrency_safe=False,
    )


async def async_build_toolkit(params: dict) -> Toolkit:
    """参数：session / user"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    view = await async_tool_view({"session": session, "user": user})
    db_policy = await async_get_db_policy({"session": session})
    email_cfg = await async_tool_config(
        {"session": session, "user_id": user.id, "category": "email"}
    )
    db_cfg = await async_tool_config(
        {"session": session, "user_id": user.id, "category": "db"}
    )
    server_db = {
        key: db_cfg.get(key)
        for key in ("db_type", "host", "port", "user", "password", "database", "path", "dir")
        if db_cfg.get(key) not in (None, "", 0)
    }
    rag_embedding = None
    try:
        rag_embedding = await rag_service._embedding(session)
    except Exception:  # noqa: BLE001 - 未配置 embedding 时不阻断其它工具
        rag_embedding = None
    email_runtime = {
        "smtp_host": email_cfg.get("smtp_host") or "",
        "smtp_port": email_cfg.get("smtp_port") or 465,
        "imap_host": email_cfg.get("imap_host") or "",
        "imap_port": email_cfg.get("imap_port") or 993,
        "host_user": email_cfg.get("host_user") or "",
        "password": email_cfg.get("password") or "",
        "profile_name": email_cfg.get("from_name") or "Agent Scope",
    }

    def build_db_data(kwargs: dict) -> dict:
        model_cfg = sanitize_model_db_config(db_policy, kwargs.get("db_config") or {})
        merged = {**model_cfg, **server_db}
        merged = apply_db_policy(db_policy, merged)
        data = {
            key: value
            for key, value in kwargs.items()
            if key not in ("db_config", "host", "port", "user", "password", "database", "path", "dir")
        }
        data["db_config"] = merged
        return data
    enabled = {
        (group["name"], tool["name"])
        for group in view["groups"]
        for tool in group["tools"]
        if tool["enabled"]
    }
    group_enabled = {group["name"]: group["enabled"] for group in view["groups"]}
    allow_shell = bool(
        await async_get_config(
            {"session": session, "key": "security.allow_agent_shell", "default": False}
        )
    )
    if not allow_shell:
        group_enabled["sys"] = False

    basic_tools = []
    if group_enabled.get("basic"):
        backend = LocalBackend(workdir=user_workspace(user.id))
        factories = {
            "Read": lambda: Read(backend=backend),
            "Write": lambda: Write(backend=backend),
            "Edit": lambda: Edit(backend=backend),
            "Glob": lambda: Glob(backend=backend),
            "Grep": lambda: Grep(backend=backend),
        }
        for name, factory in factories.items():
            if ("basic", name) in enabled:
                basic_tools.append(factory())

    plan_tools = []
    if group_enabled.get("plan"):
        factories = {
            "TaskCreate": TaskCreate,
            "TaskGet": TaskGet,
            "TaskList": TaskList,
            "TaskUpdate": TaskUpdate,
        }
        for name, factory in factories.items():
            if ("plan", name) in enabled:
                plan_tools.append(factory())

    groups = []
    if plan_tools:
        groups.append(ToolGroup(name="plan", description="结构化任务清单", tools=plan_tools))

    # 业务工具包装
    from scope.tools.db.main_db import async_db_tools, async_db_write_tools
    from scope.tools.mail.main_mail import async_email_tools
    from scope.tools.mcp.main_mcp import async_mcp_tools
    from scope.tools.net.main_crawl import async_crawl_tools
    from scope.tools.net.main_net import async_req_tools
    from scope.tools.rag.main_rag import async_rag_tools
    from scope.tools.system.main_sys import async_sys_tools
    from app.services.agent.a2a import async_a2a_tools

    async def db_read(**kwargs):
        return await async_db_tools(build_db_data(kwargs))

    async def db_write(**kwargs):
        if not db_policy["allow_write"]:
            return {"code": 403, "data": None, "message": "数据库写入已被默认策略禁用"}
        return await async_db_write_tools(build_db_data(kwargs))

    async def rag_run(**kwargs):
        data = dict(kwargs)
        data.setdefault("rag_config", rag_service._rag_config(user.id, "default"))
        if rag_embedding is not None:
            data.setdefault("embedding", rag_embedding)
        return await async_rag_tools(data)

    async def email_run(**kwargs):
        data = dict(kwargs)
        data["email_config"] = email_runtime
        return await async_email_tools(data)

    registry = {
        "db": {
            "async_db_tools": (db_read, "数据库查询"),
            "async_db_write_tools": (db_write, "数据库写入"),
        },
        "net": {
            "async_req_tools": (async_req_tools, "HTTP 请求/下载"),
            "async_crawl_tools": (async_crawl_tools, "网页抓取/截图"),
        },
        "mail": {"async_email_tools": (email_run, "邮件收发")},
        "mcp": {"async_mcp_tools": (async_mcp_tools, "MCP 客户端")},
        "sys": {"async_sys_tools": (async_sys_tools, "Shell 命令")},
        "rag": {"async_rag_tools": (rag_run, "知识库检索")},
        "a2a": {"async_a2a_tools": (async_a2a_tools, "A2A 伙伴调用")},
    }
    if db_policy["allow_write"]:
        registry["db"]["async_db_write_tools"] = (db_write, "数据库写入")
    else:
        registry["db"].pop("async_db_write_tools", None)

    for group_name, tools in registry.items():
        if not group_enabled.get(group_name):
            continue
        built = []
        for name, (fn, description) in tools.items():
            if (group_name, name) in enabled:
                built.append(_scope_tool(fn, name, description, user.id))
        if built:
            groups.append(ToolGroup(name=group_name, description=f"{group_name} 工具组", tools=built))

    return Toolkit(tools=basic_tools, tool_groups=groups)
