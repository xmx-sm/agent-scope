"""令牌签发、刷新与当前用户权限载荷。"""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError, user_public
from app.core.config import settings
from app.core.security import create_token, decode_token
from app.models import RefreshTokenSession, User
from app.models.common import new_id, utc_now
from app.services.config.service import async_get_config
from app.services.access.permissions.evaluate import async_effective_permissions


def _token_hash(token: str) -> str:
    """生成刷新令牌的数据库存储摘要。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_expired(expires_at: datetime) -> bool:
    """兼容数据库返回的无时区时间。"""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= utc_now()


async def async_revoke_refresh_tokens(params: dict) -> None:
    """撤销用户全部刷新令牌，由调用方在同一事务中提交。

    参数：session / user_id
    """
    session: AsyncSession = params["session"]
    await session.execute(
        update(RefreshTokenSession)
        .where(
            RefreshTokenSession.user_id == params["user_id"],
            RefreshTokenSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )


async def _revoke_family(session: AsyncSession, family_id: str) -> None:
    """检测到重放时撤销整个刷新令牌族。"""
    await session.execute(
        update(RefreshTokenSession)
        .where(
            RefreshTokenSession.family_id == family_id,
            RefreshTokenSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )


async def async_issue_tokens(params: dict) -> dict:
    """签发访问与刷新令牌并持久化刷新会话。

    参数：session / user
    """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    minutes = int(
        await async_get_config(
            {"session": session, "key": "session_expire_minutes", "default": 480}
        )
    )
    jti = new_id()
    family_id = new_id()
    refresh_token = create_token(
        user.id,
        user.role,
        "refresh",
        jti=jti,
        family_id=family_id,
    )
    session.add(
        RefreshTokenSession(
            id=jti,
            family_id=family_id,
            user_id=user.id,
            token_hash=_token_hash(refresh_token),
            expires_at=utc_now() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await session.commit()
    return {
        "access_token": create_token(user.id, user.role, "access", expires_minutes=minutes),
        "refresh_token": refresh_token,
        "user": user_public(user),
    }


async def async_refresh(params: dict) -> dict:
    """原子轮换刷新令牌，重放时撤销整个令牌族。

    参数：session / refresh_token
    """
    session: AsyncSession = params["session"]
    token = params["refresh_token"]
    payload = decode_token(token, expected_type="refresh")
    jti = payload.get("jti") if payload else None
    family_id = payload.get("fid") if payload else None
    user_id = payload.get("sub") if payload else None
    if not jti or not family_id or not user_id:
        raise ApiError("刷新令牌无效或已过期", code=401)

    current = (
        await session.execute(
            select(RefreshTokenSession).where(RefreshTokenSession.id == jti).with_for_update()
        )
    ).scalar_one_or_none()
    if (
        current is None
        or current.family_id != family_id
        or current.user_id != user_id
        or not hmac.compare_digest(current.token_hash, _token_hash(token))
    ):
        raise ApiError("刷新令牌无效或已过期", code=401)
    if current.revoked_at is not None or current.replaced_by_jti is not None:
        await _revoke_family(session, family_id)
        await session.commit()
        message = (
            "刷新令牌已被使用，请重新登录"
            if current.replaced_by_jti is not None
            else "刷新令牌已失效，请重新登录"
        )
        raise ApiError(message, code=401)
    if _is_expired(current.expires_at):
        raise ApiError("刷新令牌无效或已过期", code=401)

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        await _revoke_family(session, family_id)
        await session.commit()
        raise ApiError("账号不存在或已被禁用", code=401)

    minutes = int(
        await async_get_config(
            {"session": session, "key": "session_expire_minutes", "default": 480}
        )
    )
    next_jti = new_id()
    refresh_token = create_token(
        user.id,
        user.role,
        "refresh",
        jti=next_jti,
        family_id=family_id,
    )
    current.revoked_at = utc_now()
    current.replaced_by_jti = next_jti
    session.add(
        RefreshTokenSession(
            id=next_jti,
            family_id=family_id,
            user_id=user.id,
            token_hash=_token_hash(refresh_token),
            expires_at=utc_now() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await session.commit()
    return {
        "access_token": create_token(user.id, user.role, "access", expires_minutes=minutes),
        "refresh_token": refresh_token,
        "user": user_public(user),
    }


async def async_logout(params: dict) -> None:
    """撤销请求中刷新令牌所属的整个令牌族。

    参数：session / refresh_token
    """
    session: AsyncSession = params["session"]
    token = params["refresh_token"]
    payload = decode_token(token, expected_type="refresh")
    jti = payload.get("jti") if payload else None
    family_id = payload.get("fid") if payload else None
    if not jti or not family_id:
        return
    current = await session.get(RefreshTokenSession, jti)
    if (
        current is None
        or current.family_id != family_id
        or not hmac.compare_digest(current.token_hash, _token_hash(token))
    ):
        return
    await _revoke_family(session, family_id)
    await session.commit()


async def async_me_payload(params: dict) -> dict:
    """返回当前登录用户信息

    参数：session / user
    """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    return {
        "user": user_public(user),
        "permissions": await async_effective_permissions({"session": session, "user": user}),
    }
