"""用户查询与统计。"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError, user_public
from app.core.permissions import ROLES
from app.models import User


async def async_get_user_or_404(params: dict) -> User:
    """参数：session / user_id"""
    session: AsyncSession = params["session"]
    target = await session.get(User, params["user_id"])
    if target is None:
        raise ApiError("用户不存在", code=404)
    return target


async def async_list_users(params: dict) -> dict:
    """参数：session / page / page_size / keyword / role / viewer"""
    session: AsyncSession = params["session"]
    page = max(int(params.get("page") or 1), 1)
    page_size = min(max(int(params.get("page_size") or 10), 1), 100)
    keyword: str = params.get("keyword") or ""
    role: str = params.get("role") or ""
    viewer: User | None = params.get("viewer")

    conditions = []
    if viewer is not None and viewer.role != "super_admin":
        conditions.append(User.role != "super_admin")
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                User.username.ilike(like),
                User.nickname.ilike(like),
                User.email.ilike(like),
                User.phone.ilike(like),
            )
        )
    if role:
        conditions.append(User.role == role)

    total = (
        await session.execute(select(func.count()).select_from(User).where(*conditions))
    ).scalar_one()
    rows = (
        await session.execute(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    leaders = {
        user.id: user.username
        for user in (await session.execute(select(User))).scalars().all()
    }
    items = []
    for row in rows:
        item = user_public(row)
        item["leader_name"] = leaders.get(row.leader_id) if row.leader_id else None
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def async_stats(params: dict) -> dict:
    """参数：session"""
    session: AsyncSession = params["session"]
    total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    active = (
        await session.execute(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )
    ).scalar_one()
    by_role = {}
    for role in ROLES:
        by_role[role] = (
            await session.execute(
                select(func.count()).select_from(User).where(User.role == role)
            )
        ).scalar_one()
    return {"users": {"total": total, "active": active, "by_role": by_role}}
