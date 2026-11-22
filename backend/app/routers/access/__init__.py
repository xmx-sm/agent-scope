"""访问控制与 AI 工具权限路由。"""

from fastapi import APIRouter

from app.routers.access import permissions, tools

router = APIRouter()
router.include_router(permissions.router)
router.include_router(tools.router)

__all__ = ["router", "permissions", "tools"]
