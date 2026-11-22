"""Agent 长期记忆路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, ok
from app.schemas.agent.resources import MemoryToggleIn, MemoryWriteIn
from app.services.agent.memory import service as memory_service

router = APIRouter()


@router.get("/memory")
async def memory_status(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await memory_service.async_status({"session": db, "user": user}))


@router.put("/memory")
async def memory_toggle(
    body: MemoryToggleIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await memory_service.async_set_enabled(
            {"session": db, "user": user, "enabled": body.enabled}
        ),
        "长期记忆设置已保存",
    )


@router.get("/memory/files")
async def memory_files(user: CurrentUser):
    return ok(await memory_service.async_files({"user": user}))


@router.get("/memory/files/{name:path}")
async def memory_read(name: str, user: CurrentUser):
    return ok(await memory_service.async_read({"user": user, "name": name}))


@router.put("/memory/files/{name:path}")
async def memory_write(
    name: str, body: MemoryWriteIn, user: CurrentUser
):
    return ok(
        await memory_service.async_write(
            {"user": user, "name": name, "content": body.content}
        ),
        "记忆文件已保存",
    )


@router.delete("/memory/files/{name:path}")
async def memory_delete_file(name: str, user: CurrentUser):
    await memory_service.async_delete_file({"user": user, "name": name})
    return ok(None, "记忆文件已删除")


@router.delete("/memory")
async def memory_clear(user: CurrentUser):
    return ok(await memory_service.async_clear({"user": user}), "长期记忆已清空")
