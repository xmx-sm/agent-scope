"""路由层：按领域拆包，只负责解析请求并调用 services/<同名域>/。"""

from app.routers.access import router as access_router
from app.routers.account import router as account_router
from app.routers.integrations import router as integrations_router
from app.routers.system import router as system_router

__all__ = ["account_router", "access_router", "integrations_router", "system_router"]
