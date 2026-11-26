"""Agent 对话路由。"""

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import ApiError, CurrentUser, SuperAdmin, ok, require_permission
from app.models import User
from app.schemas import (
    KnowledgeSearchIn,
    LibraryCreateIn,
    LibraryShareIn,
    LibraryUpdateIn,
    ParseConfigIn,
    SubagentSaveIn,
    SuperAgentSaveIn,
    SuperConversationIn,
    A2APeerIn,
    A2AInvokeIn,
    RagSearchIn,
    ScheduledSaveIn,
    ScheduledToggleIn,
    McpSaveIn,
    ToggleIn,
    ChatStreamIn,
    ConversationBranchIn,
    ConversationCreateIn,
    ConversationRenameIn,
    ModelFetchIn,
    ToolConfigIn,
    TtsIn,
    UserAgentConfigIn,
)
from app.services.agent.conversation import conversations as conv_service
from app.services.agent.resources import mcps as mcp_service
from app.services.agent import knowledge as knowledge_service
from app.services.agent.knowledge import rag as rag_service
from app.services.agent.resources import skills as skill_service
from app.services.agent.resources import subagents as subagent_service
from app.services.agent.collaboration import super_agent as super_service
from app.services.agent.collaboration import a2a as a2a_service
from app.services.agent.automation import scheduled as scheduled_service
from app.services.agent.media import speech as speech_service
from app.services.agent.analytics import stats as stats_service
from app.services.agent.conversation import attachments as attachment_service
from app.services.agent.config import user_config as user_config_service
from app.services.access.tools import tool_config as tool_config_service
from app.services.agent.runtime.stream_manager import resume_events
from app.services.llm import providers as agent_config_service
from app.utils.mask import SENTINEL



router = APIRouter()


@router.get("/super-agent")
async def super_agent_get(
    user: CurrentUser, super_agent_id: str = "", db: AsyncSession = Depends(get_db)
):
    return ok(
        await super_service.async_get(
            {"session": db, "user_id": user.id, "super_agent_id": super_agent_id or None}
        )
    )


@router.get("/super-agents")
async def super_agent_list(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await super_service.async_list({"session": db, "user_id": user.id}))


@router.post("/super-agent")
async def super_agent_save(
    body: SuperAgentSaveIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await super_service.async_save(
            {"session": db, "user_id": user.id, "data": body.model_dump()}
        ),
        "超级智能体已保存",
    )


@router.delete("/super-agent")
async def super_agent_delete(
    user: CurrentUser, super_agent_id: str = "", db: AsyncSession = Depends(get_db)
):
    await super_service.async_delete(
        {"session": db, "user_id": user.id, "super_agent_id": super_agent_id or None}
    )
    return ok(None, "已删除")


@router.post("/super-agent/main-conversation")
async def super_main_conversation(
    body: SuperConversationIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await super_service.async_create_conversation(
            {
                "session": db,
                "user_id": user.id,
                "super_agent_id": body.super_agent_id,
                "member_id": body.member_id,
                "role": body.role,
                "title": body.title,
            }
        ),
        "主会话已创建",
    )


@router.post("/super-agent/conversation")
async def super_member_conversation(
    body: SuperConversationIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await super_service.async_create_conversation(
            {
                "session": db,
                "user_id": user.id,
                "super_agent_id": body.super_agent_id,
                "member_id": body.member_id,
                "role": body.role,
                "title": body.title,
            }
        ),
        "会话已创建",
    )


# ==================== A2A 管理面 ====================



@router.get("/a2a/peers")
async def a2a_peers(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await a2a_service.async_list_peers({"session": db, "user": user}))


@router.post("/a2a/peers")
async def a2a_peer_save(
    body: A2APeerIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_save_peer(
            {"session": db, "user": user, "data": body.model_dump()}
        ),
        "伙伴已保存",
    )


@router.delete("/a2a/peers/{peer_id}")
async def a2a_peer_delete(
    peer_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await a2a_service.async_delete_peer({"session": db, "user": user, "peer_id": peer_id})
    return ok(None, "已删除")


@router.post("/a2a/peers/{peer_id}/rotate")
async def a2a_peer_rotate(
    peer_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_rotate_key({"session": db, "user": user, "peer_id": peer_id}),
        "密钥已重置",
    )


@router.get("/a2a/peers/{peer_id}/key")
async def a2a_peer_key(
    peer_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_reveal_key({"session": db, "user": user, "peer_id": peer_id})
    )


@router.post("/a2a/peers/{peer_id}/test")
async def a2a_peer_test(
    peer_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_test_peer({"session": db, "user": user, "peer_id": peer_id}),
        "连接成功",
    )


@router.post("/a2a/invoke")
async def a2a_invoke(
    body: A2AInvokeIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_invoke_peer(
            {
                "session": db,
                "user": user,
                "peer": body.peer,
                "message": body.message,
                "session_hint": body.session_hint,
            }
        )
    )


@router.get("/a2a/invocations")
async def a2a_invocations(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await a2a_service.async_invocations({"session": db, "user": user}))



@router.get("/a2a/sessions")
async def a2a_sessions(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await a2a_service.async_sessions({"session": db, "user": user}))


@router.delete("/a2a/sessions/{session_id}")
async def a2a_forget_session(
    session_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await a2a_service.async_forget_session(
        {"session": db, "user": user, "session_id": session_id}
    )
    return ok(None, "协作记忆已清除")
