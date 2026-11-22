"""认证路由：只做参数解析和响应包装。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, ok
from app.schemas import ChangePasswordIn, LoginIn, RefreshIn, RegisterIn
from app.services.auth import login as login_service
from app.services.auth import password as password_service
from app.services.auth import register as register_service
from app.services.auth import token as token_service

router = APIRouter(prefix="/auth", tags=["认证"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


@router.post("/register")
async def register(body: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)):
    result = await register_service.async_register(
        {"session": db, "data": body.model_dump(), "ip": _client_ip(request)}
    )
    return ok(result, "注册成功")


@router.post("/login")
async def login(body: LoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    result = await login_service.async_login(
        {
            "session": db,
            "account": body.account,
            "password": body.password,
            "ip": _client_ip(request),
        }
    )
    return ok(result, "登录成功")


@router.post("/refresh")
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    result = await token_service.async_refresh(
        {"session": db, "refresh_token": body.refresh_token}
    )
    return ok(result, "刷新成功")


@router.get("/me")
async def me(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await token_service.async_me_payload({"session": db, "user": user}))


@router.post("/change-password")
async def change_password(
    body: ChangePasswordIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await password_service.async_change_password(
        {
            "session": db,
            "user": user,
            "old_password": body.old_password,
            "new_password": body.new_password,
        }
    )
    return ok(None, "密码已修改")
