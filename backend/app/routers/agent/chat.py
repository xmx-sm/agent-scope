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
from app.services.agent.runtime.stream_manager import resume_events, stream_events
from app.services.llm import providers as agent_config_service
from app.utils.mask import SENTINEL



router = APIRouter()


@router.get("/stats")
async def agent_stats(
    user: CurrentUser, days: int = 7, db: AsyncSession = Depends(get_db)
):
    return ok(
        await stats_service.async_stats(
            {"session": db, "user_id": user.id, "days": days}
        )
    )


@router.get("/conversations")
async def list_conversations(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await conv_service.async_list_conversations({"session": db, "user_id": user.id}))


@router.post("/conversations")
async def create_conversation(
    body: ConversationCreateIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await conv_service.async_create_conversation(
            {"session": db, "user_id": user.id, "title": body.title}
        ),
        "会话已创建",
    )


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: ConversationRenameIn,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await conv_service.async_rename_conversation(
            {"session": db, "user_id": user.id, "conversation_id": conversation_id,
             "title": body.title}
        ),
        "会话已重命名",
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await conv_service.async_delete_conversation(
        {"session": db, "user_id": user.id, "conversation_id": conversation_id}
    )
    return ok(None, "会话已删除")


@router.post("/conversations/{conversation_id}/branch")
async def branch_conversation(
    conversation_id: str,
    body: ConversationBranchIn,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await conv_service.async_branch_conversation(
            {
                "session": db,
                "user_id": user.id,
                "conversation_id": conversation_id,
                "message_id": body.message_id,
            }
        ),
        "分支已创建",
    )


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await conv_service.async_list_messages(
            {"session": db, "user_id": user.id, "conversation_id": conversation_id}
        )
    )


@router.get("/chat/resume/{conversation_id}")
async def chat_resume(
    conversation_id: str,
    user: User = Depends(require_permission("ai.use")),
):
    return StreamingResponse(
        resume_events({"user_id": user.id, "conversation_id": conversation_id}),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamIn,
    user: User = Depends(require_permission("ai.use")),
):
    return StreamingResponse(
        stream_events(
            {
                "user_id": user.id,
                "conversation_id": body.conversation_id,
                "content": body.content,
                "attachment_ids": body.attachment_ids,
            }
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ==================== 超级智能体 ====================
