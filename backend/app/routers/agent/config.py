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


@router.get("/tool-config/{category}")
async def get_tool_config(
    category: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await tool_config_service.async_view(
            {"session": db, "user_id": user.id, "category": category}
        )
    )


@router.put("/tool-config/{category}")
async def save_tool_config(
    category: str, body: ToolConfigIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await tool_config_service.async_save(
            {
                "session": db,
                "user": user,
                "category": category,
                "data": body.model_dump(),
            }
        ),
        "工具配置已保存",
    )


@router.delete("/tool-config/{category}")
async def reset_tool_config(
    category: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await tool_config_service.async_reset(
            {"session": db, "user": user, "category": category}
        ),
        "已恢复系统默认",
    )


@router.post("/tool-config/{category}/test")
async def test_tool_config(
    category: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    if category == "email":
        data = await tool_config_service.async_test_email(
            {"session": db, "user_id": user.id}
        )
    elif category == "db":
        data = await tool_config_service.async_test_db(
            {"session": db, "user_id": user.id}
        )
    else:
        raise ApiError("未知工具配置类别")
    return ok(data, "连接成功")



@router.get("/providers")
async def user_providers(_: CurrentUser):
    return ok(agent_config_service.PROVIDERS)


@router.get("/config")
async def get_agent_config(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await user_config_service.async_view({"session": db, "user": user}))


@router.put("/config")
async def save_agent_config(
    body: UserAgentConfigIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await user_config_service.async_save(
            {"session": db, "user": user, "data": body.model_dump()}
        ),
        "Agent 配置已保存",
    )


@router.delete("/config")
async def reset_agent_config(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(
        await user_config_service.async_reset({"session": db, "user": user}),
        "已恢复跟随系统默认",
    )


@router.post("/models")
async def fetch_user_models(
    body: ModelFetchIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    effective = await user_config_service.async_effective({"session": db, "user": user})
    api_key = body.api_key
    if not api_key or api_key == SENTINEL:
        api_key = str(effective.get("api_key") or "")
    base_url = body.base_url or str(effective.get("base_url") or "")
    provider = body.provider or str(effective.get("provider") or "")
    return ok(
        await agent_config_service.async_fetch_models(
            {
                "provider": provider,
                "base_url": base_url,
                "api_key": api_key,
            }
        ),
        "模型列表已获取",
    )
