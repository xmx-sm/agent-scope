"""Agent 对话路由。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, ok, require_permission
from app.models import User
from app.schemas import ChatStreamIn, ConversationCreateIn
from app.services.agent import conversations as conv_service
from app.services.agent.chat import async_stream_chat

router = APIRouter(prefix="/agent", tags=["Agent 对话"])


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
