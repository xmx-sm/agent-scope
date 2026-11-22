"""AI 工具权限变更留痕。"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ToolPermissionAudit


def snapshot(params: dict) -> str | None:
    """生成工具授权快照 JSON。参数：enabled / granted_by。"""
    enabled = params.get("enabled")
    if enabled is None:
        return None
    return json.dumps(
        {"enabled": enabled, "granted_by": params.get("granted_by")}, ensure_ascii=False
    )


async def add_audit(params: dict) -> None:
    """写入工具权限变更审计。参数：session / user_id / actor_id / action / tool_group / tool_name / before / after。"""
    session: AsyncSession = params["session"]
    session.add(
        ToolPermissionAudit(
            user_id=params["user_id"],
            actor_id=params["actor_id"],
            action=params["action"],
            tool_group=params.get("tool_group"),
            tool_name=params.get("tool_name"),
            prev_state=params.get("before"),
            new_state=params.get("after"),
        )
    )


async def async_list_audits(params: dict) -> dict:
    """分页查询工具权限审计

    参数：session / page / page_size / user_id / actor_id
    """
    session: AsyncSession = params["session"]
    page = max(int(params.get("page") or 1), 1)
    page_size = min(max(int(params.get("page_size") or 20), 1), 100)
    stmt = select(ToolPermissionAudit).order_by(ToolPermissionAudit.created_at.desc())
    if params.get("user_id"):
        stmt = stmt.where(ToolPermissionAudit.user_id == params["user_id"])
    if params.get("actor_id"):
        stmt = stmt.where(ToolPermissionAudit.actor_id == params["actor_id"])
    rows = (
        await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "actor_id": row.actor_id,
                "action": row.action,
                "tool_group": row.tool_group,
                "tool_name": row.tool_name,
                "prev_state": row.prev_state,
                "new_state": row.new_state,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
    }
