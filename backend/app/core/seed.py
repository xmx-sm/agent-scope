"""首次启动种子数据：默认账号、默认配置、角色权限。

幂等：已存在的记录不覆盖（重启不会改回默认值）。
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Menu, RolePermission, SystemConfig, User
from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS, ROLE_LABELS
from app.services.config.meta import CONFIG_DEFINITIONS
from app.core.security import hash_password

logger = logging.getLogger("seed")

# 内置账号：登录名 / 昵称 / 角色 / 上级登录名
SEED_USERS: list[dict[str, Any]] = [
    {"username": "MX", "nickname": "MX", "role": "super_admin", "leader": None,
     "email": "mx@example.com"},
    {"username": "张三", "nickname": "张三", "role": "admin", "leader": None,
     "email": "zhangsan@example.com"},
    {"username": "李四", "nickname": "李四", "role": "user", "leader": "张三",
     "email": "lisi@example.com"},
]
SEED_PASSWORD = "990108"

# 默认菜单：两级结构，parent_key 为空表示一级
SEED_MENUS: list[dict[str, Any]] = [
    {"key": "dashboard", "parent_key": None, "title": "工作台", "path": "/dashboard",
     "icon": "Grid", "permission": "dashboard", "super_only": False, "sort_order": 10},
    {"key": "menu.chat", "parent_key": None, "title": "AI 对话", "path": "/chat",
     "icon": "ChatDotRound", "permission": "ai.use", "super_only": False, "sort_order": 15},
    {"key": "group.personal", "parent_key": None, "title": "我的", "path": "",
     "icon": "User", "permission": None, "super_only": False, "sort_order": 20},
    {"key": "menu.my_permissions", "parent_key": "group.personal", "title": "我的权限",
     "path": "/permissions", "icon": "Key", "permission": "permissions.self",
     "super_only": False, "sort_order": 10},
    {"key": "menu.personalize", "parent_key": "group.personal", "title": "菜单个性化",
     "path": "/menu-settings", "icon": "Setting", "permission": "dashboard",
     "super_only": False, "sort_order": 20},
    {"key": "menu.agent_settings", "parent_key": "group.personal", "title": "Agent 设置",
     "path": "/agent-settings", "icon": "Cpu", "permission": "ai.use",
     "super_only": False, "sort_order": 25},
    {"key": "profile", "parent_key": "group.personal", "title": "个人中心",
     "path": "/profile", "icon": "User", "permission": "profile",
     "super_only": False, "sort_order": 30},
    {"key": "menu.team", "parent_key": None, "title": "管理下级",
     "path": "/team/permissions", "icon": "UserFilled", "permission": "permissions.team",
     "super_only": False, "leader_only": True, "sort_order": 30},
    {"key": "group.system", "parent_key": None, "title": "系统", "path": "",
     "icon": "Monitor", "permission": None, "super_only": False, "sort_order": 40},
    {"key": "menu.users", "parent_key": "group.system", "title": "用户管理",
     "path": "/admin/users", "icon": "UserFilled", "permission": "admin.users",
     "super_only": True, "sort_order": 10},
    {"key": "menu.status", "parent_key": "group.system", "title": "运行信息",
     "path": "/system/status", "icon": "Monitor", "permission": "system.status",
     "super_only": False, "sort_order": 20},
    {"key": "group.config", "parent_key": None, "title": "默认配置", "path": "",
     "icon": "Setting", "permission": None, "super_only": False, "sort_order": 50},
    {"key": "menu.config.system", "parent_key": "group.config", "title": "系统设置",
     "path": "/admin/config/system", "icon": "Setting", "permission": "admin.settings",
     "super_only": True, "sort_order": 10},
    {"key": "menu.config.roles", "parent_key": "group.config", "title": "角色权限",
     "path": "/admin/config/roles", "icon": "Lock", "permission": "admin.permissions",
     "super_only": True, "sort_order": 20},
    {"key": "menu.config.menus", "parent_key": "group.config", "title": "菜单配置",
     "path": "/admin/config/menus", "icon": "Menu", "permission": "admin.menus",
     "super_only": True, "sort_order": 30},
    {"key": "menu.agent", "parent_key": "group.config", "title": "Agent 配置",
     "path": "/admin/agent", "icon": "Cpu", "permission": "ai.config",
     "super_only": True, "sort_order": 40},
]

async def async_seed(params: dict) -> None:
    """参数：session"""
    session: AsyncSession = params["session"]
    created_users = 0
    for spec in SEED_USERS:
        exists = (
            await session.execute(select(User).where(User.username == spec["username"]))
        ).scalar_one_or_none()
        if exists:
            continue
        user = User(
            username=spec["username"],
            nickname=spec["nickname"],
            email=spec["email"],
            role=spec["role"],
            password_hash=hash_password(SEED_PASSWORD),
            is_active=True,
        )
        session.add(user)
        await session.flush()
        created_users += 1

    # 汇报线：等张三落库后再设置李四的 leader_id
    for spec in SEED_USERS:
        if not spec["leader"]:
            continue
        user = (
            await session.execute(select(User).where(User.username == spec["username"]))
        ).scalar_one_or_none()
        leader = (
            await session.execute(select(User).where(User.username == spec["leader"]))
        ).scalar_one_or_none()
        if user and leader and not user.leader_id:
            user.leader_id = leader.id

    created_configs = 0
    for item in CONFIG_DEFINITIONS:
        key = item["key"]
        exists = await session.get(SystemConfig, key)
        if exists:
            continue
        session.add(
            SystemConfig(
                key=key,
                value=json.dumps(item["value"], ensure_ascii=False),
                label=item["label"],
                description=item["description"],
                value_type=item["type"],
            )
        )
        created_configs += 1

    created_menus = 0
    layout_marker = await session.get(SystemConfig, "__meta.menu_layout_v4")
    if layout_marker is None:
        legacy_keys = [
            "group.permissions", "menu.settings", "menu.team_permissions", "menu.admin",
            "menu.config",
        ]
        for key in legacy_keys:
            row = (
                await session.execute(select(Menu).where(Menu.key == key))
            ).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
        # 同 key 的默认菜单同步为新布局（parent/title/order 等）
        for spec in SEED_MENUS:
            row = (
                await session.execute(select(Menu).where(Menu.key == spec["key"]))
            ).scalar_one_or_none()
            if row is not None:
                for field, value in spec.items():
                    if field != "key":
                        setattr(row, field, value)
        session.add(
            SystemConfig(
                key="__meta.menu_layout_v4",
                value='"4"',
                label="内部：菜单布局版本",
                description="内部迁移标记，不在默认设置中展示",
                value_type="string",
            )
        )
        await session.flush()

    for spec in SEED_MENUS:
        exists = (
            await session.execute(select(Menu).where(Menu.key == spec["key"]))
        ).scalar_one_or_none()
        if exists:
            continue
        session.add(Menu(**spec))
        created_menus += 1

    created_roles = 0
    for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        exists = await session.get(RolePermission, role)
        if exists:
            continue
        session.add(
            RolePermission(role=role, permissions=json.dumps(permissions, ensure_ascii=False))
        )
        created_roles += 1

    # 超管角色恒为全部权限（含新增项）
    super_row = await session.get(RolePermission, "super_admin")
    if super_row is not None:
        super_row.permissions = json.dumps(
            [item["key"] for item in PERMISSIONS], ensure_ascii=False
        )

    # 升级兼容：老版本角色权限补上新增的基础权限点，并剔除超管专属项
    assignable = {item["key"] for item in PERMISSIONS if not item.get("super_only")}
    for role in ("admin", "user"):
        row = await session.get(RolePermission, role)
        if row is None:
            continue
        current = json.loads(row.permissions or "[]")
        changed = False
        if "permissions.self" not in current:
            current.append("permissions.self")
            changed = True
        if role == "admin" and "permissions.team" not in current:
            current.append("permissions.team")
            changed = True
        if "ai.use" not in current:
            current.append("ai.use")
            changed = True
        filtered = sorted(item for item in current if item in assignable)
        if filtered != sorted(json.loads(row.permissions or "[]")):
            changed = True
        if changed:
            row.permissions = json.dumps(filtered, ensure_ascii=False)

    await session.commit()
    if created_users or created_configs or created_roles or created_menus:
        logger.info(
            "种子数据写入：用户 %s / 配置 %s / 角色 %s / 菜单 %s（角色：%s）",
            created_users, created_configs, created_roles, created_menus,
            "、".join(f"{k}={v}" for k, v in ROLE_LABELS.items()),
        )
