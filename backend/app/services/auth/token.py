"""令牌签发、刷新与当前用户权限载荷。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError, user_public
from app.core.security import create_token, decode_token
from app.models import User
from app.services.config.service import async_get_config
from app.services.permissions.evaluate import async_effective_permissions


async def async_issue_tokens(params: dict) -> dict:
    """参数：session / user"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    minutes = int(
        await async_get_config(
            {"session": session, "key": "session_expire_minutes", "default": 480}
        )
    )
    return {
        "access_token": create_token(user.id, user.role, "access", expires_minutes=minutes),
        "refresh_token": create_token(user.id, user.role, "refresh"),
        "user": user_public(user),
    }


async def async_refresh(params: dict) -> dict:
    """参数：session / refresh_token"""
    session: AsyncSession = params["session"]
    payload = decode_token(params["refresh_token"], expected_type="refresh")
    if not payload:
        raise ApiError("刷新令牌无效或已过期", code=401)
    user = await session.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise ApiError("账号不存在或已被禁用", code=401)
    return await async_issue_tokens({"session": session, "user": user})


async def async_me_payload(params: dict) -> dict:
    """参数：session / user"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    return {
        "user": user_public(user),
        "permissions": await async_effective_permissions({"session": session, "user": user}),
    }
