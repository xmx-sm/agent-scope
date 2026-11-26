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


@router.post("/tts")
async def agent_tts(body: TtsIn, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await speech_service.async_synthesize(
        {"session": db, "text": body.text, "voice": body.voice, "model": body.model}
    )
    return Response(
        content=result["audio"],
        media_type=result["media_type"],
        headers={"X-Tts-Bytes": str(result["bytes"])},
    )
