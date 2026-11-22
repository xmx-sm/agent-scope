"""注册业务。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError, user_public
from app.core.security import hash_password
from app.models import User
from app.services.account.auth.rate_limit import async_rate_limit
from app.services.account.auth.token import async_issue_tokens
from app.services.config.service import async_get_config
from app.services.access.tools.policy import async_apply_new_user
from app.services.account.user.common import async_assert_unique, clean_optional


async def async_register(params: dict) -> dict:
    """注册用户

    参数：session / data / ip
    """
    session: AsyncSession = params["session"]
    data: dict = params["data"]
    ip: str = params["ip"]

    await async_rate_limit(
        {
            "session": session,
            "key": f"rl:register:{ip}",
            "max_key": "register_max_attempts",
            "window_key": "register_window_seconds",
            "max_default": 5,
            "window_default": 1800,
        }
    )
    if not await async_get_config(
        {"session": session, "key": "allow_register", "default": True}
    ):
        raise ApiError("当前未开放注册，请联系管理员")

    username = data["username"].strip()
    nickname = clean_optional({"value": data.get("nickname")}) or username
    email = clean_optional({"value": data.get("email")})
    phone = clean_optional({"value": data.get("phone")})
    password = data["password"]

    min_length = int(
        await async_get_config(
            {"session": session, "key": "password_min_length", "default": 6}
        )
    )
    if len(password) < min_length:
        raise ApiError(f"密码长度不能少于 {min_length} 位")

    await async_assert_unique(
        {"session": session, "username": username, "email": email, "phone": phone}
    )
    if (await session.execute(select(User.id).where(User.nickname == nickname))).first():
        raise ApiError("该昵称已被使用")

    role = str(
        await async_get_config({"session": session, "key": "default_role", "default": "user"})
    )
    if role not in ("user", "admin"):
        role = "user"

    user = User(
        username=username,
        nickname=nickname,
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    await async_apply_new_user({"session": session, "user": user})
    return {
        "user": user_public(user),
        "tokens": await async_issue_tokens({"session": session, "user": user}),
    }
