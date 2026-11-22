"""用户写操作：新增、修改、删除、重置密码。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError, user_public
from app.core.permissions import ROLES
from app.core.security import hash_password
from app.models import User
from app.services.user.common import async_assert_unique, clean_optional


async def async_create_user(params: dict) -> dict:
    """参数：session / data / operator"""
    session: AsyncSession = params["session"]
    data: dict = params["data"]
    operator: User | None = params.get("operator")

    role = data.get("role") or "user"
    if role not in ROLES:
        raise ApiError("无效的角色")
    if operator is not None and operator.role != "super_admin" and role == "super_admin":
        raise ApiError("仅超级管理员可创建超级管理员", code=403)

    username = data["username"].strip()
    email = clean_optional(data.get("email"))
    phone = clean_optional(data.get("phone"))
    nickname = clean_optional(data.get("nickname")) or username
    await async_assert_unique(
        {"session": session, "username": username, "email": email, "phone": phone}
    )
    if (await session.execute(select(User.id).where(User.nickname == nickname))).first():
        raise ApiError("该昵称已被使用")

    user = User(
        username=username,
        nickname=nickname,
        email=email,
        phone=phone,
        password_hash=hash_password(data["password"]),
        role=role,
        leader_id=data.get("leader_id") or None,
        is_active=data.get("is_active", True),
        avatar=clean_optional(data.get("avatar")),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user_public(user)


async def _async_assert_super_admin_remains(params: dict) -> None:
    """参数：session / exclude_id"""
    session: AsyncSession = params["session"]
    remaining = (
        await session.execute(
            select(func.count()).select_from(User).where(
                User.role == "super_admin",
                User.id != params["exclude_id"],
                User.is_active.is_(True),
            )
        )
    ).scalar_one()
    if remaining == 0:
        raise ApiError("至少保留一名启用状态的超级管理员")


async def async_update_user(params: dict) -> dict:
    """参数：session / user_id / data / operator"""
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    data: dict = params["data"]
    operator: User | None = params.get("operator")

    user = await session.get(User, user_id)
    if user is None:
        raise ApiError("用户不存在", code=404)
    if operator is not None and operator.role != "super_admin":
        if user.role == "super_admin":
            raise ApiError("无权修改超级管理员", code=403)
        if data.get("role") == "super_admin":
            raise ApiError("仅超级管理员可授予超级管理员角色", code=403)

    role = data.get("role")
    if role is not None:
        if role not in ROLES:
            raise ApiError("无效的角色")
        if user.role == "super_admin" and role != "super_admin":
            await _async_assert_super_admin_remains(
                {"session": session, "exclude_id": user.id}
            )
        user.role = role

    if "nickname" in data and data["nickname"] is not None:
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

    for field, label in (("email", "邮箱"), ("phone", "手机号")):
        if field not in data:
            continue
        value = clean_optional(data[field])
        if value:
            conflict = (
                await session.execute(
                    select(User.id).where(getattr(User, field) == value, User.id != user.id)
                )
            ).first()
            if conflict:
                raise ApiError(f"该{label}已被使用")
        setattr(user, field, value)

    if "avatar" in data:
        user.avatar = clean_optional(data["avatar"])

    if "leader_id" in data:
        leader_id = data["leader_id"] or None
        if leader_id == user.id:
            raise ApiError("不能将自己设为上级")
        if leader_id and await session.get(User, leader_id) is None:
            raise ApiError("指定的上级不存在")
        user.leader_id = leader_id

    if data.get("is_active") is not None:
        is_active = bool(data["is_active"])
        if not is_active and user.role == "super_admin":
            await _async_assert_super_admin_remains(
                {"session": session, "exclude_id": user.id}
            )
        user.is_active = is_active

    await session.commit()
    await session.refresh(user)
    return user_public(user)


async def async_delete_user(params: dict) -> None:
    """参数：session / user_id / operator"""
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    operator: User = params["operator"]
    if user_id == operator.id:
        raise ApiError("不能删除当前登录账号")
    user = await session.get(User, user_id)
    if user is None:
        raise ApiError("用户不存在", code=404)
    if operator.role != "super_admin" and user.role == "super_admin":
        raise ApiError("无权删除超级管理员", code=403)
    if user.role == "super_admin":
        await _async_assert_super_admin_remains({"session": session, "exclude_id": user.id})

    subordinates = (
        await session.execute(select(User).where(User.leader_id == user.id))
    ).scalars().all()
    for subordinate in subordinates:
        subordinate.leader_id = None
    await session.delete(user)
    await session.commit()


async def async_reset_password(params: dict) -> None:
    """参数：session / user_id / new_password / operator"""
    session: AsyncSession = params["session"]
    user = await session.get(User, params["user_id"])
    if user is None:
        raise ApiError("用户不存在", code=404)
    operator: User | None = params.get("operator")
    if operator is not None and operator.role != "super_admin" and user.role == "super_admin":
        raise ApiError("无权重置超级管理员密码", code=403)
    user.password_hash = hash_password(params["new_password"])
    await session.commit()
