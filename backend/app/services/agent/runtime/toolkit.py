"""按 AI 工具权限构建 AgentScope Toolkit。"""

from __future__ import annotations

import os
import re
from typing import Any, Awaitable, Callable

from agentscope.tool import (
    # ---- 公网部署安全策略：禁用本地文件读取/写入/编辑/搜索（2026-11-23）----
    # Edit,
    FunctionTool,
    # Glob,
    # Grep,
    # LocalBackend,
    # Read,
    TaskCreate,
    TaskGet,
    TaskList,
    TaskUpdate,
    ToolGroup,
    Toolkit,
    # Write,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
# from app.services.agent.knowledge import rag as rag_service  # 公网部署：禁用 RAG 工具
from app.services.agent.runtime.scope_bridge import ROOT  # noqa: F401 确保 scope 路径已注入
from app.services.agent.runtime.scope_bridge import user_workspace
from app.services.config.service import async_get_config
# from app.services.access.security.db_policy import (  # 公网部署：禁用数据库工具
#     apply_db_policy,
#     async_get_db_policy,
#     sanitize_model_db_config,
# )
from app.services.access.security.guard import _redact_obj
from app.services.access.security.identity import merge_identity
from app.services.access.tools.evaluate import async_tool_view
from app.services.access.tools.tool_config import async_effective as async_tool_config


def _within(root: str, path: str) -> bool:
    """判断 path 是否位于 root 目录内（按真实路径，防符号链接逃逸）。"""
    try:
        target = os.path.realpath(os.path.abspath(path))
        base = os.path.realpath(os.path.abspath(root))
    except OSError:
        return False
    return target == base or target.startswith(base + os.sep)


def _sandbox_tool_files(fn: Callable[..., Awaitable[Any]], user_id: str,
                        default_mail_dir: bool = False) -> Callable[..., Awaitable[Any]]:
    """限制工具只能读写当前用户目录内的本地文件。

    net / mail 组默认可用：
    - download / screenshot 的 save_path、邮件附件目录会写盘；
    - extract_pdf 的 pdf_path、邮件 attachments 会读本地文件。
    若不在服务端做路径约束，用户可以借这些参数覆盖 backend/.env 或读取源码。

    写入只允许在个人 workspace；读取额外允许 user_<id>/attachments 等用户目录内容。
    """
    workspace = user_workspace({"user_id": user_id})
    user_root = os.path.dirname(workspace)

    async def call(**kwargs):
        # 邮件附件默认落在个人 workspace，避免落到服务端 cwd。
        if default_mail_dir and not kwargs.get("attachment_dir"):
            kwargs["attachment_dir"] = os.path.join(workspace, "email_attachments")
        for key in ("save_path", "attachment_dir"):
            value = kwargs.get(key)
            if value in (None, ""):
                continue
            if not _within(workspace, str(value)):
                return {
                    "code": 400,
                    "data": None,
                    "message": f"错误：{key} 必须位于用户工作目录内（{workspace}）",
                }
        read_paths = [kwargs.get("pdf_path")]
        attachments = kwargs.get("attachments")
        if isinstance(attachments, (list, tuple)):
            read_paths.extend(attachments)
        for value in read_paths:
            if value in (None, ""):
                continue
            if not _within(user_root, str(value)):
                return {
                    "code": 400,
                    "data": None,
                    "message": f"错误：文件路径必须位于用户目录内（{user_root}）",
                }
        return await fn(**kwargs)

    return call


def _scope_tool(fn: Callable[..., Awaitable[Any]], name: str, description: str,
                user_id: str) -> FunctionTool:
    """内部辅助函数：_scope_tool。
    参数：fn / name / description / user_id。
    """
    async def call(**kwargs):
        """包装 scope 工具并注入服务端身份。"""
        result = await fn(
            merge_identity(
                {"identity": {"user_id": user_id, "_actor_kind": "ai"}, "params": kwargs}
            )
        )
        return _redact_obj(result)

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
    """按用户权限构建 AgentScope Toolkit

    参数：session / user
    """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    view = await async_tool_view({"session": session, "user": user})
    # ---- 公网部署安全策略：禁用数据库与 RAG 工具（2026-11-23）----
    # db_policy = await async_get_db_policy({"session": session})
    email_cfg = await async_tool_config(
        {"session": session, "user_id": user.id, "category": "email"}
    )
    # db_cfg = await async_tool_config(
    #     {"session": session, "user_id": user.id, "category": "db"}
    # )
    # server_db = {
    #     key: db_cfg.get(key)
    #     for key in ("db_type", "host", "port", "user", "password", "database", "path", "dir")
    #     if db_cfg.get(key) not in (None, "", 0)
    # }
    # rag_embedding = None
    # try:
    #     rag_embedding = await rag_service._embedding(session)
    # except Exception:  # noqa: BLE001 - 未配置 embedding 时不阻断其它工具
    #     rag_embedding = None
    email_runtime = {
        "smtp_host": email_cfg.get("smtp_host") or "",
        "smtp_port": email_cfg.get("smtp_port") or 465,
        "imap_host": email_cfg.get("imap_host") or "",
        "imap_port": email_cfg.get("imap_port") or 993,
        "host_user": email_cfg.get("host_user") or "",
        "password": email_cfg.get("password") or "",
        "profile_name": email_cfg.get("from_name") or "Agent Scope",
    }

    # def build_db_data(kwargs: dict) -> dict:
    #     """合并数据库策略与用户连接配置。"""
    #     model_cfg = sanitize_model_db_config({"policy": db_policy, "db_config": kwargs.get("db_config") or {}})
    #     merged = {**model_cfg, **server_db}
    #     merged = apply_db_policy({"policy": db_policy, "db_config": merged})
    #     data = {
    #         key: value
    #         for key, value in kwargs.items()
    #         if key not in ("db_config", "host", "port", "user", "password", "database", "path", "dir")
    #     }
    #     data["db_config"] = merged
    #     return data
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
    # ---- 公网部署安全策略：禁用系统文件夹访问（2026-11-23）----
    # 基础工具会通过 LocalBackend 读写/搜索 backend/uploads/agents 下的本地文件，
    # 公网部署存在越权与信息泄露风险，默认不注册。恢复前请确认目录隔离与鉴权。
    # if group_enabled.get("basic"):
    #     backend = LocalBackend(workdir=user_workspace({"user_id": user.id}))
    #     factories = {
    #         "Read": lambda: Read(backend=backend),
    #         "Write": lambda: Write(backend=backend),
    #         "Edit": lambda: Edit(backend=backend),
    #         "Glob": lambda: Glob(backend=backend),
    #         "Grep": lambda: Grep(backend=backend),
    #     }
    #     for name, factory in factories.items():
    #         if ("basic", name) in enabled:
    #             basic_tools.append(factory())

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
    # from scope.tools.db.main_db import async_db_tools, async_db_write_tools  # 公网部署：禁用数据库工具
    from scope.tools.mail.main_mail import async_email_tools
    from scope.tools.mcp.main_mcp import async_mcp_tools
    from scope.tools.net.main_crawl import async_crawl_tools
    from scope.tools.net.main_net import async_req_tools
    # from scope.tools.rag.main_rag import async_rag_tools  # 公网部署：禁用 RAG 工具
    # from scope.tools.system.main_sys import async_sys_tools  # 公网部署：禁用 Shell 工具
    from app.services.agent.collaboration.a2a import (
        async_a2a_tools,
        async_invoke_peer_by_name,
        async_peer_specs,
    )

    # ---- 公网部署安全策略：禁用数据库工具与 RAG 工具（2026-11-23）----
    # async def db_read(**kwargs):
    #     """数据库只读工具。"""
    #     return await async_db_tools(build_db_data(kwargs))
    #
    # async def db_write(**kwargs):
    #     """数据库写入工具。"""
    #     if not db_policy["allow_write"]:
    #         return {"code": 403, "data": None, "message": "数据库写入已被默认策略禁用"}
    #     return await async_db_write_tools(build_db_data(kwargs))
    #
    # async def rag_run(**kwargs):
    #     """知识库工具入口。"""
    #     data = dict(kwargs)
    #     data.setdefault("rag_config", rag_service._rag_config(user.id, "default"))
    #     if rag_embedding is not None:
    #         data.setdefault("embedding", rag_embedding)
    #     return await async_rag_tools(data)

    async def email_run(**kwargs):
        """邮件工具入口。"""
        data = dict(kwargs)
        data["email_config"] = email_runtime
        return await async_email_tools(data)

    registry = {
        # ---- 公网部署安全策略：禁用数据库工具（2026-11-23）----
        # "db": {
        #     "async_db_tools": (db_read, "数据库查询"),
        #     "async_db_write_tools": (db_write, "数据库写入"),
        # },
        "net": {
            "async_req_tools": (_sandbox_tool_files(async_req_tools, user.id), "HTTP 请求/下载"),
            "async_crawl_tools": (_sandbox_tool_files(async_crawl_tools, user.id), "网页抓取/截图"),
        },
        "mail": {
            "async_email_tools": (
                _sandbox_tool_files(email_run, user.id, default_mail_dir=True),
                "邮件收发",
            )
        },
        "mcp": {"async_mcp_tools": (async_mcp_tools, "MCP 客户端")},
        # ---- 公网部署安全策略：禁用 Shell 命令执行（2026-11-23）----
        # "sys": {"async_sys_tools": (async_sys_tools, "Shell 命令")},
        # ---- 公网部署安全策略：禁用 RAG 工具（2026-11-23）----
        # "rag": {"async_rag_tools": (rag_run, "知识库检索")},
        "a2a": {"async_a2a_tools": (async_a2a_tools, "A2A 伙伴调用")},
    }
    # if db_policy["allow_write"]:
    #     registry["db"]["async_db_write_tools"] = (db_write, "数据库写入")
    # else:
    #     registry["db"].pop("async_db_write_tools", None)

    for group_name, tools in registry.items():
        if not group_enabled.get(group_name):
            continue
        built = []
        for name, (fn, description) in tools.items():
            if (group_name, name) in enabled:
                built.append(_scope_tool(fn, name, description, user.id))
        if built:
            groups.append(ToolGroup(name=group_name, description=f"{group_name} 工具组", tools=built))

    a2a_group = next((group for group in groups if group.name == "a2a"), None)
    if a2a_group is not None:
        peers = await async_peer_specs({"session": session, "user": user})
        used_names: set[str] = set()
        for index, peer in enumerate(peers, 1):
            slug = re.sub(r"[^A-Za-z0-9]+", "_", peer["name"]).strip("_")[:24]
            tool_name = f"a2a_{slug}" if slug else f"a2a_peer_{index}"
            while tool_name in used_names:
                tool_name = f"{tool_name}_{index}"
            used_names.add(tool_name)

            async def call_peer(message: str = "", _peer_name: str = peer["name"]):
                """调用指定 A2A 伙伴。"""
                return await async_invoke_peer_by_name(
                    {
                        "user_id": user.id,
                        "peer": _peer_name,
                        "message": message,
                        "session_hint": "default",
                    }
                )

            basic_tools.append(
                FunctionTool(
                    call_peer,
                    name=tool_name,
                    description=(
                        f"调用 A2A 伙伴「{peer['name']}」。"
                        f"{peer.get('description') or ''} "
                        "该工具自动复用该伙伴的固定远端上下文，不需要传会话 ID。"
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "要发送给伙伴的内容"},
                        },
                        "required": ["message"],
                        "additionalProperties": False,
                    },
                    is_concurrency_safe=False,
                )
            )

    return Toolkit(tools=basic_tools, tool_groups=groups)
