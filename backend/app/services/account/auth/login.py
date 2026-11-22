"""登录业务。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.security import verify_password
from app.services.account.auth.rate_limit import async_rate_limit
from app.services.account.auth.token import async_issue_tokens
from app.services.config.service import async_get_config
from app.services.account.user.common import async_find_by_identifier
from app.utils.rate_limiter import rate_limiter


async def async_login(params: dict) -> dict:
    """参数：session / account / password / ip"""
    session: AsyncSession = params["session"]
    account: str = params["account"]
    password: str = params["password"]
    ip: str = params["ip"]

    key = f"rl:login:{account.strip().lower()}:{ip}"
    await async_rate_limit(
        {
            "session": session,
            "key": key,
            "max_key": "login_max_attempts",
            "window_key": "login_window_seconds",
            "max_default": 10,
            "window_default": 900,
        }
    )

    user = await async_find_by_identifier({"session": session, "account": account})
    if user is None or not verify_password(password, user.password_hash):
        raise ApiError("账号或密码错误", code=401)
    if not user.is_active:
        raise ApiError("账号已被禁用", code=403)

    maintenance = bool(
        await async_get_config(
            {"session": session, "key": "maintenance_mode", "default": False}
        )
    )
    if maintenance and user.role != "super_admin":
        raise ApiError("系统维护中，请稍后再试", code=503)

    await rate_limiter.clear(key)
    return await async_issue_tokens({"session": session, "user": user})
