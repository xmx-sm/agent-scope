"""修改密码业务。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.security import hash_password, verify_password
from app.models import User
from app.services.config.service import async_get_config


async def async_change_password(params: dict) -> None:
    """修改密码

    参数：session / user / old_password / new_password
    """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    old_password: str = params["old_password"]
    new_password: str = params["new_password"]

    if not verify_password(old_password, user.password_hash):
        raise ApiError("原密码错误")
    min_length = int(
        await async_get_config(
            {"session": session, "key": "password_min_length", "default": 6}
        )
    )
    if len(new_password) < min_length:
        raise ApiError(f"密码长度不能少于 {min_length} 位")
    user.password_hash = hash_password(new_password)
    await session.commit()
