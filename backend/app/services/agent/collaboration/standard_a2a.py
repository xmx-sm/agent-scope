"""标准 A2A（Agent2Agent Protocol v1.0）服务端适配。

平台原来的 ``/a2a/agents`` + ``/a2a/invoke`` 是自定义 A2A Lite。
本模块用官方 ``a2a-sdk`` 提供标准 JSON-RPC 绑定：

- ``GET /.well-known/agent-card.json``：Agent Card
- ``POST {api_prefix}/a2a``：JSON-RPC（SendMessage / GetTask / ListTasks / CancelTask ...）
- 入站鉴权继续复用平台 ``A2APeer`` 的 ``X-Api-Key``
- 每个标准 A2A ``context_id`` 映射到平台的一个 Agent 会话
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from a2a.auth.user import User as A2AUser
from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.routes.common import DefaultServerCallContextBuilder
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types.a2a_pb2 import (
    APIKeySecurityScheme,
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Part,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)
from a2a.utils.constants import PROTOCOL_VERSION_1_0
from a2a.utils.errors import InvalidRequestError
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import A2APeer, AgentConversation
from app.services.agent.collaboration.a2a import resolve_inbound_peer

logger = logging.getLogger("a2a-standard")


def build_agent_card(params: dict | None = None) -> AgentCard:
    """构建标准 A2A Agent Card。"""
    params = params or {}
    base = (params.get("public_base_url") or settings.a2a_public_url or "").rstrip("/")
    if not base:
        base = f"http://127.0.0.1:{settings.port}"
    rpc_url = f"{base}{settings.api_prefix}/a2a"
    return AgentCard(
        name=settings.a2a_agent_name,
        description=settings.a2a_agent_description,
        version="0.26.0",
        supported_interfaces=[
            AgentInterface(
                url=rpc_url,
                protocol_binding="JSONRPC",
                protocol_version=PROTOCOL_VERSION_1_0,
            )
        ],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/plain", "application/json"],
        skills=[
            AgentSkill(
                id="general",
                name="通用智能体",
                description="Agent Scope 通用对话、知识库与工具调用",
                tags=["agent", "chat", "tools"],
            )
        ],
        security_schemes={
            "apiKey": SecurityScheme(
                api_key_security_scheme=APIKeySecurityScheme(
                    location="header",
                    name="X-Api-Key",
                )
            )
        },
        security_requirements=[
            SecurityRequirement(schemes={"apiKey": StringList(list=[])})
        ],
    )


def _header_value(scope: dict[str, Any], name: bytes) -> str:
    """从 ASGI scope 中读取指定请求头。"""
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


async def _resolve_peer_id(api_key: str) -> str:
    """把入站 API Key 解析为已启用的伙伴 ID。"""
    async with AsyncSessionLocal() as session:
        peer = await resolve_inbound_peer({"session": session, "api_key": api_key})
    return peer.id if peer is not None else ""


class A2AAuthMiddleware:
    """只对标准 A2A JSON-RPC 路径做 X-Api-Key 鉴权。

    Agent Card 是公开发现文档，不要求鉴权；JSON-RPC 数据面必须带有效 Key。
    """

    def __init__(self, app):
        """保存下一个 ASGI 应用。"""
        self.app = app

    async def __call__(self, scope, receive, send):
        """拦截标准 A2A JSON-RPC 请求并校验伙伴 Key。"""
        path = str(scope.get("path") or "").rstrip("/")
        rpc_path = f"{settings.api_prefix}/a2a".rstrip("/")
        if (
            scope.get("type") == "http"
            and path == rpc_path
            and scope.get("method") != "OPTIONS"
        ):
            key = _header_value(scope, b"x-api-key")
            peer_id = await _resolve_peer_id(key) if key else ""
            if not peer_id:
                response = JSONResponse(
                    status_code=401,
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32000,
                            "message": "Unauthorized: invalid X-Api-Key",
                        },
                    },
                )
                await response(scope, receive, send)
                return
            scope.setdefault("state", {})["a2a_peer_id"] = peer_id
        await self.app(scope, receive, send)


class _PeerUser(A2AUser):
    """以 A2APeer.id 作为 A2A TaskStore 的 owner scope，隔离不同伙伴的任务。"""

    def __init__(self, peer_id: str) -> None:
        """绑定负责当前任务隔离的伙伴 ID。"""
        self._peer_id = peer_id

    @property
    def is_authenticated(self) -> bool:
        """标识中间件已通过鉴权。"""
        return bool(self._peer_id)

    @property
    def user_name(self) -> str:
        """返回 A2A SDK 使用的伙伴标识。"""
        return self._peer_id


class A2APeerContextBuilder(DefaultServerCallContextBuilder):
    """把中间件解析出的 peer 注入 A2A ServerCallContext。"""

    def build(self, request: Request) -> ServerCallContext:
        """把中间件解析出的伙伴注入任务上下文。"""
        context = super().build(request)
        peer_id = str(request.scope.get("state", {}).get("a2a_peer_id", ""))
        context.state["a2a_peer_id"] = peer_id
        if peer_id:
            context.user = _PeerUser(peer_id)
        return context


async def _get_peer(context: RequestContext) -> A2APeer | None:
    """加载当前请求关联且允许入站的伙伴。"""
    peer_id = str(context.call_context.state.get("a2a_peer_id") or "")
    if not peer_id:
        return None
    async with AsyncSessionLocal() as session:
        peer = await session.get(A2APeer, peer_id)
        if (
            peer is None
            or not peer.is_active
            or peer.direction not in ("inbound", "both")
        ):
            return None
        return peer


async def _ensure_conversation(peer: A2APeer, context_id: str, title: str) -> str:
    """把标准 A2A context_id 映射到平台 Agent 会话。"""
    async with AsyncSessionLocal() as session:
        conv = await session.get(AgentConversation, context_id)
        if conv is not None:
            if conv.user_id != peer.owner_user_id:
                raise InvalidRequestError(message="A2A context_id 已被占用")
            return conv.id
        conv = AgentConversation(
            id=context_id,
            user_id=peer.owner_user_id,
            title=f"[A2A] {peer.name} · {title}"[:200],
            origin="a2a",
        )
        session.add(conv)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            conv = await session.get(AgentConversation, context_id)
            if conv is None or conv.user_id != peer.owner_user_id:
                raise
        return context_id


class ScopeA2AExecutor(AgentExecutor):
    """把标准 A2A Task 桥接到平台 ``async_run_turn``。"""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """执行标准 A2A 消息并回传平台 Agent 结果。"""
        peer = await _get_peer(context)
        if peer is None:
            raise InvalidRequestError(message="无效的 A2A 凭据")

        task = context.current_task
        if task is None:
            if context.message is None:
                raise InvalidRequestError(message="缺少 A2A message")
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        text = context.get_user_input("\n").strip()
        if not text:
            await updater.reject(
                updater.new_agent_message([Part(text="当前仅支持文本消息")])
            )
            return

        try:
            conversation_id = await _ensure_conversation(
                peer, task.context_id, text
            )
            from app.services.agent.conversation.chat import async_run_turn

            result = await async_run_turn(
                {
                    "user_id": peer.owner_user_id,
                    "conversation_id": conversation_id,
                    "content": text,
                    "super_depth": 1,
                    "tools_enabled": bool(peer.allow_tools),
                    "source": "a2a",
                }
            )
            content = str(result.get("content") or "")
            if content:
                await updater.add_artifact(
                    [Part(text=content, media_type="text/plain")],
                    name="result",
                )
            await updater.complete()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 任务失败必须转成标准 FAILED
            logger.exception("standard A2A task failed")
            await updater.failed(
                updater.new_agent_message([Part(text=f"执行失败：{exc}")])
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """按 A2A SDK 约定取消当前任务。"""
        task = context.current_task
        if task is None:
            return
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.cancel(
            updater.new_agent_message([Part(text="任务已取消")])
        )


def register_standard_a2a(params: dict) -> None:
    """注册标准 A2A routes；未启用或依赖缺失时不影响主服务。"""
    if not settings.a2a_standard_enabled:
        return
    try:
        app = params["app"]
        card = build_agent_card()
        handler = DefaultRequestHandler(
            agent_executor=ScopeA2AExecutor(),
            task_store=InMemoryTaskStore(),
            agent_card=card,
        )
        rpc_path = f"{settings.api_prefix}/a2a"
        jsonrpc_routes = create_jsonrpc_routes(
            handler,
            rpc_url=rpc_path,
            context_builder=A2APeerContextBuilder(),
            enable_v0_3_compat=True,
        )
        card_routes = create_agent_card_routes(card)
        card_routes += create_agent_card_routes(
            card,
            card_url=f"{settings.api_prefix}/.well-known/agent-card.json",
        )
        add_a2a_routes_to_fastapi(
            app,
            agent_card_routes=card_routes,
            jsonrpc_routes=jsonrpc_routes,
        )
        app.add_middleware(A2AAuthMiddleware)
        logger.info("标准 A2A 已启用：%s", rpc_path)
    except Exception:  # noqa: BLE001 - 可选依赖/配置问题不能拖垮主服务
        logger.exception("标准 A2A 注册失败，已跳过")


__all__ = [
    "A2AAuthMiddleware",
    "A2APeerContextBuilder",
    "ScopeA2AExecutor",
    "build_agent_card",
    "register_standard_a2a",
]
