"""首次启动种子数据：默认账号、默认配置、角色权限。

幂等：已存在的记录不覆盖（重启不会改回默认值）。
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import RolePermission, SystemConfig, User
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
        filtered = sorted(item for item in current if item in assignable)
        if filtered != sorted(json.loads(row.permissions or "[]")):
            changed = True
        if changed:
            row.permissions = json.dumps(filtered, ensure_ascii=False)

    await session.commit()
    if created_users or created_configs or created_roles:
        logger.info(
            "种子数据写入：用户 %s / 配置 %s / 角色 %s（角色：%s）",
            created_users, created_configs, created_roles,
            "、".join(f"{k}={v}" for k, v in ROLE_LABELS.items()),
        )
