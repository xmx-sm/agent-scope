"""机器人管理与 Webhook 路由。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import ok, require_permission
from app.schemas.integrations.bot import BotCreateIn, BotUpdateIn
from app.services.integrations.bots import service, webhook

router = APIRouter(tags=["机器人"])


@router.get("/bots")
async def list_bots(
    user=Depends(require_permission("bots.manage")),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的机器人。"""
    return ok(await service.async_list({"session": db, "user": user}))


@router.post("/bots")
async def create_bot(
    body: BotCreateIn,
    user=Depends(require_permission("bots.manage")),
    db: AsyncSession = Depends(get_db),
):
    """创建机器人并返回一次性接入密钥。"""
    return ok(await service.async_create({"session": db, "user": user, "data": body.model_dump()}))


@router.get("/bots/{bot_id}")
async def get_bot(
    bot_id: str,
    user=Depends(require_permission("bots.manage")),
    db: AsyncSession = Depends(get_db),
):
    """查看机器人详情。"""
    return ok(
        await service.async_get({"session": db, "user": user, "bot_id": bot_id})
    )


@router.patch("/bots/{bot_id}")
async def update_bot(
    bot_id: str,
    body: BotUpdateIn,
    user=Depends(require_permission("bots.manage")),
    db: AsyncSession = Depends(get_db),
):
    """更新机器人名称、启停、工具权限和超时。"""
    return ok(
        await service.async_update(
            {
                "session": db,
                "user": user,
                "bot_id": bot_id,
                "data": body.model_dump(exclude_unset=True),
            }
        )
    )


@router.delete("/bots/{bot_id}")
async def delete_bot(
    bot_id: str,
    user=Depends(require_permission("bots.manage")),
    db: AsyncSession = Depends(get_db),
):
    """删除机器人。"""
    await service.async_delete({"session": db, "user": user, "bot_id": bot_id})
    return ok(None, "机器人已删除")


@router.post("/bots/{bot_id}/rotate-secret")
async def rotate_bot_secret(
    bot_id: str,
    user=Depends(require_permission("bots.manage")),
    db: AsyncSession = Depends(get_db),
):
    """轮换机器人接入密钥。"""
    return ok(await service.async_rotate_secret({"session": db, "user": user, "bot_id": bot_id}))


@router.post("/public/bots/{bot_id}/webhook")
async def bot_webhook(bot_id: str, request: Request):
    """接收第三方机器人消息并同步返回 AI 回复。"""
    return ok(await webhook.async_handle_webhook({"request": request, "bot_id": bot_id}))
