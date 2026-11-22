"""菜单查询与可见性计算。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Menu, User
from app.services.permissions.evaluate import async_effective_permissions


def menu_public(row: Menu) -> dict[str, Any]:
    return {
        "id": row.id,
        "key": row.key,
        "parent_key": row.parent_key,
        "title": row.title,
        "path": row.path,
        "icon": row.icon,
        "permission": row.permission,
        "super_only": row.super_only,
        "sort_order": row.sort_order,
        "is_visible": row.is_visible,
    }


async def async_list_all(params: dict) -> dict:
    """参数：session"""
    session: AsyncSession = params["session"]
    rows = (
        await session.execute(select(Menu).order_by(Menu.sort_order, Menu.key))
    ).scalars().all()
    return {"menus": [menu_public(row) for row in rows]}


async def async_mine(params: dict) -> list[dict[str, Any]]:
    """参数：session / user，返回按权限过滤后的两级菜单树。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]

    effective = set(
        await async_effective_permissions({"session": session, "user": user})
    )
    rows = (
        await session.execute(
            select(Menu)
            .where(Menu.is_visible.is_(True))
            .order_by(Menu.sort_order, Menu.key)
        )
    ).scalars().all()

    def allowed(row: Menu) -> bool:
        if row.super_only and user.role != "super_admin":
            return False
        if row.permission and row.permission not in effective:
            return False
        return True

    roots: list[dict[str, Any]] = []
    children: dict[str, list[dict[str, Any]]] = {}
    node_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not allowed(row):
            continue
        node = menu_public(row)
        node["children"] = []
        node_by_key[row.key] = node
        if row.parent_key:
            children.setdefault(row.parent_key, []).append(node)
        else:
            roots.append(node)

    for key, items in children.items():
        parent = node_by_key.get(key)
        if parent is not None:
            parent["children"] = items

    result = []
    for node in roots:
        if node["path"]:
            result.append(node)
        elif node["children"]:
            result.append(node)
    return result
