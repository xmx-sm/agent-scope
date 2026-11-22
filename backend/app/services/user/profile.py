"""个人资料业务。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError, user_public
from app.models import User
from app.services.user.common import clean_optional


async def async_update_profile(params: dict) -> dict:
    """参数：session / user / data"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    data: dict = params["data"]

    if data.get("nickname") is not None:
        nickname = data["nickname"].strip()
        if not nickname:
            raise ApiError("昵称不能为空")
        conflict = (
            await session.execute(
                select(User.id).where(User.nickname == nickname, User.id != user.id)
            )
        ).first()
        if conflict:
            raise ApiError("该昵称已被使用")
        user.nickname = nickname

    if data.get("avatar") is not None:
        avatar = data["avatar"].strip()
        if avatar and not (
            avatar.startswith("http://")
            or avatar.startswith("https://")
            or avatar.startswith("/")
        ):
            raise ApiError("头像需为 http(s) 链接或站内路径")
        user.avatar = avatar or None

    for field, label in (("email", "邮箱"), ("phone", "手机号")):
        value = data.get(field)
        if value is None:
            continue
        value = clean_optional(value)
        if value:
            conflict = (
                await session.execute(
                    select(User.id).where(getattr(User, field) == value, User.id != user.id)
                )
            ).first()
            if conflict:
                raise ApiError(f"该{label}已被使用")
        setattr(user, field, value)

    await session.commit()
    await session.refresh(user)
    return user_public(user)
