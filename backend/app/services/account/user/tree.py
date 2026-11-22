"""组织汇报线：下属树与上下级判断。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def async_descendants(params: dict) -> list[User]:
    """查询用户的所有下级

    参数：session / user_id
    """
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    rows = (await session.execute(select(User))).scalars().all()
    children: dict[str, list[User]] = {}
    for row in rows:
        if row.leader_id:
            children.setdefault(row.leader_id, []).append(row)

    result: list[User] = []
    queue = list(children.get(user_id, []))
    seen: set[str] = {user_id}
    while queue:
        current = queue.pop(0)
        if current.id in seen:
            continue
        seen.add(current.id)
        result.append(current)
        queue.extend(children.get(current.id, []))
    return result


async def async_is_descendant(params: dict) -> bool:
    """判断上下级关系

    参数：session / ancestor_id / target_id
    """
    ancestor_id: str = params["ancestor_id"]
    target_id: str = params["target_id"]
    if ancestor_id == target_id:
        return False
    users = await async_descendants(
        {"session": params["session"], "user_id": ancestor_id}
    )
    return any(user.id == target_id for user in users)
