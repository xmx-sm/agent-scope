"""Agent 对话路由。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import ApiError, CurrentUser, ok, require_permission
from app.models import User
from app.schemas import ChatStreamIn, ConversationCreateIn, ModelFetchIn, ToolConfigIn, UserAgentConfigIn
from app.services.agent import conversations as conv_service
from app.services.agent import user_config as user_config_service
from app.services.tools import tool_config as tool_config_service
from app.services.agent.chat import async_stream_chat
from app.services.config import agent as agent_config_service
from app.utils.mask import SENTINEL

router = APIRouter(prefix="/agent", tags=["Agent 对话"])


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


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await conv_service.async_delete_conversation(
        {"session": db, "user_id": user.id, "conversation_id": conversation_id}
    )
    return ok(None, "会话已删除")


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await conv_service.async_list_messages(
            {"session": db, "user_id": user.id, "conversation_id": conversation_id}
        )
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamIn,
    user: User = Depends(require_permission("ai.use")),
):
    return StreamingResponse(
        async_stream_chat(user.id, body.conversation_id, body.content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
