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
from app.services.agent import stats as stats_service
from app.services.agent.conversation import attachments as attachment_service
from app.services.agent.config import user_config as user_config_service
from app.services.tools import tool_config as tool_config_service
from app.services.agent.runtime.stream_manager import resume_events, stream_events
from app.services.config import agent as agent_config_service
from app.utils.mask import SENTINEL



router = APIRouter()


@router.post("/attachments")
async def upload_attachment(
    user: CurrentUser, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    return ok(
        await attachment_service.async_upload({"session": db, "user": user, "file": file}),
        "附件已上传",
    )


@router.get("/skills")
async def list_skills(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await skill_service.async_list({"session": db, "user": user}))


@router.post("/skills/upload")
async def upload_skill(
    user: CurrentUser,
    file: UploadFile = File(...),
    name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    return ok(
        await skill_service.async_upload_zip(
            {
                "session": db,
                "user": user,
                "filename": file.filename or "skill.zip",
                "content": content,
                "name": name,
            }
        ),
        "技能已上传",
    )


@router.patch("/skills/{skill_id}")
async def toggle_skill(
    skill_id: str, body: ToggleIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await skill_service.async_toggle(
            {"session": db, "user": user, "skill_id": skill_id, "is_active": body.is_active}
        )
    )


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await skill_service.async_delete({"session": db, "user": user, "skill_id": skill_id})
    return ok(None, "技能已删除")


@router.get("/subagents")
async def list_subagents(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await subagent_service.async_list({"session": db, "user": user}))


@router.post("/subagents")
async def save_subagent(
    body: SubagentSaveIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await subagent_service.async_save(
            {"session": db, "user": user, "data": body.model_dump()}
        ),
        "子智能体已保存",
    )


@router.delete("/subagents/{subagent_id}")
async def delete_subagent(
    subagent_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await subagent_service.async_delete(
        {"session": db, "user": user, "subagent_id": subagent_id}
    )
    return ok(None, "子智能体已删除")


@router.get("/mcps")
async def list_mcps(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await mcp_service.async_list({"session": db, "user": user}))


@router.post("/mcps")
async def save_mcp(
    body: McpSaveIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await mcp_service.async_save({"session": db, "user": user, "data": body.model_dump()}),
        "MCP 已保存",
    )


@router.delete("/mcps/{mcp_id}")
async def delete_mcp(mcp_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await mcp_service.async_delete({"session": db, "user": user, "mcp_id": mcp_id})
    return ok(None, "MCP 已删除")
