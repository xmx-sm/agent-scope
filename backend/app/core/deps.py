"""通用响应、异常与鉴权依赖。"""

from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import User
from app.core.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


class ApiError(Exception):
    """业务异常：默认 HTTP 200 + code!=200，前端按 code 提示。"""

    def __init__(self, msg: str, code: int = 400, status_code: int | None = None):
        super().__init__(msg)
        self.msg = msg
        self.code = code
        self.status_code = status_code if status_code is not None else (401 if code == 401 else 200)


def ok(data: Any = None, msg: str = "success") -> dict[str, Any]:
    return {"code": 200, "data": data, "msg": msg}


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "data": None, "msg": exc.msg},
    )


def user_public(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "email": user.email,
        "phone": user.phone,
        "avatar": user.avatar,
        "role": user.role,
        "leader_id": user.leader_id,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise ApiError("未登录或登录已过期", code=401)
    payload = decode_token(credentials.credentials)
    if not payload:
        raise ApiError("未登录或登录已过期", code=401)
    user = (await db.execute(select(User).where(User.id == payload.get("sub")))).scalar_one_or_none()
    if user is None:
        raise ApiError("账号不存在", code=401)
    if not user.is_active:
        raise ApiError("账号已被禁用", code=403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_super_admin(user: CurrentUser) -> User:
    if user.role != "super_admin":
        raise ApiError("仅超级管理员可操作", code=403)
    return user


SuperAdmin = Annotated[User, Depends(require_super_admin)]


def require_permission(permission: str):
    """按「用户有效权限」校验；超级管理员始终放行。"""

    async def dependency(
        user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
    ) -> User:
        if user.role == "super_admin":
            return user
        from app.services.permissions.evaluate import async_effective_permissions

        if permission not in await async_effective_permissions({"session": db, "user": user}):
            raise ApiError("没有访问该功能的权限", code=403)
        return user

    return dependency


UsersAdmin = Annotated[User, Depends(require_super_admin)]
