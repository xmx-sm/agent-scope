"""Agent 路由包：按领域拆分子路由。"""

from fastapi import APIRouter

from app.routers.agent import (
    admin,
    automation,
    chat,
    collaboration,
    config,
    knowledge,
    media,
    memory,
    public_a2a,
    resources,
)

router = APIRouter(prefix="/agent", tags=["Agent 对话"])
for module in (config, chat, knowledge, resources, collaboration, automation, media, memory):
    router.include_router(module.router)

admin_router = APIRouter(prefix="/admin/agent", tags=["Agent 管理"])
admin_router.include_router(admin.router)

public_router = public_a2a.router

__all__ = ["router", "admin_router", "public_router"]
