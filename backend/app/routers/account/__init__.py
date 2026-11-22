"""账号与用户路由。"""

from fastapi import APIRouter

from app.routers.account import auth, user

router = APIRouter()
router.include_router(auth.router)
router.include_router(user.router)

__all__ = ["router", "auth", "user"]
