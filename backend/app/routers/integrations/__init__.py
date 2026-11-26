"""集成领域路由。"""

from app.routers.integrations.bots import router as bots_router

router = bots_router

__all__ = ["bots_router", "router"]
