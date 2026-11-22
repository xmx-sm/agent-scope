"""系统、配置与菜单路由。"""

from fastapi import APIRouter

from app.routers.system import config, menu, system

router = APIRouter()
router.include_router(system.router)
router.include_router(config.router)
router.include_router(menu.router)

__all__ = ["router", "system", "config", "menu"]
