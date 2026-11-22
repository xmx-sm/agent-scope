"""菜单写操作与排序。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.permissions import ALL_PERMISSION_KEYS
from app.models import Menu
from app.services.menu import query as menu_query
from app.services.menu.query import menu_public


def _validate_permission(params: dict) -> None:
    permission = params.get("permission")
    if permission and permission not in ALL_PERMISSION_KEYS:
        raise ApiError(f"未知权限点：{permission}")


async def _async_validate_parent(params: dict) -> None:
    session: AsyncSession = params["session"]
    parent_key = params.get("parent_key")
    current_key = params.get("current_key")
    if not parent_key:
        return
    if parent_key == current_key:
        raise ApiError("父级不能是自己")
    parent = (
        await session.execute(select(Menu).where(Menu.key == parent_key))
    ).scalar_one_or_none()
    if parent is None:
        raise ApiError("父级菜单不存在")
    if parent.parent_key:
        raise ApiError("菜单只支持两级：父级必须是一级菜单")


async def async_create_menu(params: dict) -> dict:
    """参数：session / data"""
    session: AsyncSession = params["session"]
    data: dict = params["data"]
    exists = (
        await session.execute(select(Menu).where(Menu.key == data["key"]))
    ).scalar_one_or_none()
    if exists:
        raise ApiError("菜单 key 已存在")
    _validate_permission({"permission": data.get("permission")})
    await _async_validate_parent({"session": session, "parent_key": data.get("parent_key")})

    row = Menu(
        key=data["key"],
        parent_key=data.get("parent_key") or None,
        title=data["title"],
        path=data.get("path") or "",
        icon=data.get("icon") or "Menu",
        permission=data.get("permission") or None,
        super_only=bool(data.get("super_only")),
        leader_only=bool(data.get("leader_only")),
        sort_order=int(data.get("sort_order") or 100),
        is_visible=bool(data.get("is_visible", True)),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return menu_public(row)


async def async_update_menu(params: dict) -> dict:
    """参数：session / menu_id / data"""
    session: AsyncSession = params["session"]
    row = await session.get(Menu, params["menu_id"])
    if row is None:
        raise ApiError("菜单不存在", code=404)
    data: dict = params["data"]

    if "parent_key" in data:
        await _async_validate_parent(
            {"session": session, "parent_key": data.get("parent_key"), "current_key": row.key}
        )
        row.parent_key = data.get("parent_key") or None
    if "permission" in data:
        _validate_permission({"permission": data.get("permission")})
        row.permission = data.get("permission") or None
    for field in ("title", "path", "icon"):
        if field in data and data[field] is not None:
            setattr(row, field, data[field])
    if data.get("super_only") is not None:
        row.super_only = bool(data["super_only"])
    if data.get("leader_only") is not None:
        row.leader_only = bool(data["leader_only"])
    if data.get("sort_order") is not None:
        row.sort_order = int(data["sort_order"])
    if data.get("is_visible") is not None:
        row.is_visible = bool(data["is_visible"])

    await session.commit()
    await session.refresh(row)
    return menu_public(row)


async def async_delete_menu(params: dict) -> None:
    """参数：session / menu_id"""
    session: AsyncSession = params["session"]
    row = await session.get(Menu, params["menu_id"])
    if row is None:
        raise ApiError("菜单不存在", code=404)
    has_children = (
        await session.execute(select(Menu.id).where(Menu.parent_key == row.key))
    ).first()
    if has_children:
        raise ApiError("请先删除或移动子菜单")
    await session.delete(row)
    await session.commit()


async def async_reorder_menus(params: dict) -> dict:
    """参数：session / ids（按目标顺序排列的菜单 ID）"""
    session: AsyncSession = params["session"]
    ids: list[str] = params["ids"]
    if not ids:
        raise ApiError("排序列表不能为空")
    rows = (
        await session.execute(select(Menu).where(Menu.id.in_(ids)))
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    for index, menu_id in enumerate(ids, start=1):
        row = by_id.get(menu_id)
        if row is not None:
            row.sort_order = index * 10
    await session.commit()
    return await menu_query.async_list_all({"session": session})

