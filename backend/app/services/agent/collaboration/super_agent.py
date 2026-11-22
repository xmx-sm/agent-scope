"""超级智能体配置与会话装配。"""

from __future__ import annotations

import json

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import AgentConversation, SuperAgentConfig, SuperAgentMember, User
from app.services.agent.config.user_config import async_effective
from app.utils.mask import SENTINEL, mask_secret

MAX_SUBS = 20
LLM_FIELDS = (
    "provider", "base_url", "api_key", "model", "temperature", "max_tokens",
    "context_window", "stream", "think", "thinking_budget", "reasoning_effort",
)


def _load(raw: str | None) -> dict:
    """内部辅助函数：_load。
    参数：raw。
    """
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _member_dict(row: SuperAgentMember) -> dict:
    """内部辅助函数：_member_dict。
    参数：row。
    """
    llm = _load(row.llm_config)
    if llm.get("api_key"):
        llm["api_key"] = mask_secret(llm["api_key"])
    return {
        "id": row.id,
        "role": row.role,
        "name": row.name,
        "description": row.description,
        "system_prompt": row.system_prompt,
        "llm_config": llm,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
    }


async def _cfg_dict(session: AsyncSession, cfg: SuperAgentConfig) -> dict:
    """内部辅助函数：_cfg_dict。
    参数：session / cfg。
    """
    rows = (
        await session.execute(
            select(SuperAgentMember)
            .where(SuperAgentMember.super_agent_id == cfg.id)
            .order_by(SuperAgentMember.sort_order, SuperAgentMember.created_at)
        )
    ).scalars().all()
    main = next((row for row in rows if row.role == "main"), None)
    return {
        "id": cfg.id,
        "name": cfg.name,
        "description": cfg.description,
        "enabled": cfg.enabled,
        "main": _member_dict(main) if main else None,
        "subs": [_member_dict(row) for row in rows if row.role != "main"],
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


async def async_list(params: dict) -> list[dict]:
    """列出当前用户的超级智能体。

        参数：session / user_id。
        """
    session: AsyncSession = params["session"]
    rows = (
        await session.execute(
            select(SuperAgentConfig)
            .where(SuperAgentConfig.user_id == params["user_id"])
            .order_by(SuperAgentConfig.created_at)
        )
    ).scalars().all()
    return [await _cfg_dict(session, row) for row in rows]


async def async_get(params: dict) -> dict | None:
    """获取单个超级智能体配置。

        参数：super_agent_id / session / user_id。
        """
    session: AsyncSession = params["session"]
    cfg = await _get_cfg(session, params["user_id"], params.get("super_agent_id"))
    return await _cfg_dict(session, cfg) if cfg else None


async def _get_cfg(
    session: AsyncSession, user_id: str, super_agent_id: str | None = None
) -> SuperAgentConfig | None:
    """内部辅助函数：_get_cfg。
    参数：session / user_id / super_agent_id。
    """
    stmt = select(SuperAgentConfig).where(SuperAgentConfig.user_id == user_id)
    if super_agent_id:
        stmt = stmt.where(SuperAgentConfig.id == super_agent_id)
    return (
        await session.execute(stmt.order_by(SuperAgentConfig.created_at).limit(1))
    ).scalar_one_or_none()


async def _members(session: AsyncSession, agent_id: str) -> list[SuperAgentMember]:
    """内部辅助函数：_members。
    参数：session / agent_id。
    """
    return list(
        (
            await session.execute(
                select(SuperAgentMember)
                .where(SuperAgentMember.super_agent_id == agent_id)
                .order_by(SuperAgentMember.sort_order, SuperAgentMember.created_at)
            )
        ).scalars().all()
    )


async def async_save(params: dict) -> dict:
    """整体保存超级智能体主/子成员。

        参数：session / user_id / data。
        """
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    data: dict = params["data"]
    main = data.get("main") or {}
    subs = data.get("subs") or []
    name = str(data.get("name") or "").strip() or "超级智能体"
    if not str(main.get("name") or "").strip():
        raise ApiError("主智能体名称不能为空")
    if not str(main.get("system_prompt") or "").strip():
        raise ApiError("主智能体提示词不能为空")
    if len(subs) > MAX_SUBS:
        raise ApiError(f"子智能体最多 {MAX_SUBS} 个")

    cfg = await _get_cfg(session, user_id, data.get("id"))
    if data.get("id") and cfg is None:
        raise ApiError("超级智能体不存在", code=404)
    if cfg is None:
        dup = (
            await session.execute(
                select(SuperAgentConfig).where(
                    SuperAgentConfig.user_id == user_id, SuperAgentConfig.name == name
                )
            )
        ).scalar_one_or_none()
        if dup:
            raise ApiError(f"超级智能体「{name}」已存在")
        cfg = SuperAgentConfig(user_id=user_id, name=name)
        session.add(cfg)
        await session.flush()
    cfg.name = name
    cfg.description = str(data.get("description") or "")[:500]
    if "enabled" in data:
        cfg.enabled = bool(data["enabled"])

    old = {row.id: row for row in await _members(session, cfg.id)}
    keep: set[str] = set()
    used_names: set[str] = set()
    for role, payload in [("main", main)] + [("sub", item) for item in subs]:
        member_name = str(payload.get("name") or "").strip()
        if not member_name:
            raise ApiError("成员名称不能为空")
        if member_name in used_names:
            raise ApiError(f"成员名称「{member_name}」重复")
        used_names.add(member_name)
        row = old.get(payload.get("id")) if payload.get("id") else None
        if payload.get("id") and row is None:
            raise ApiError(f"成员「{member_name}」不属于该超级智能体", code=404)
        if row is None:
            row = SuperAgentMember(
                user_id=user_id, super_agent_id=cfg.id, role=role, name=member_name
            )
            session.add(row)
            old[row.id] = row
        row.role = role
        row.name = member_name
        row.description = str(payload.get("description") or "")[:500]
        if "system_prompt" in payload:
            row.system_prompt = str(payload.get("system_prompt") or "")
        if "llm_config" in payload:
            incoming = payload.get("llm_config") or {}
            previous = _load(row.llm_config)
            merged = dict(previous)
            for key in LLM_FIELDS:
                if key not in incoming:
                    continue
                value = incoming[key]
                if key == "api_key" and value == SENTINEL:
                    continue
                merged[key] = value
            row.llm_config = json.dumps(merged, ensure_ascii=False)
        row.sort_order = int(payload.get("sort_order") or (0 if role == "main" else 1))
        if "is_active" in payload:
            row.is_active = bool(payload["is_active"])
        elif row.is_active is None:
            row.is_active = True
        keep.add(row.id)

    gone = [member_id for member_id in old if member_id not in keep]
    if gone:
        bound = set(
            (
                await session.execute(
                    select(AgentConversation.super_agent_member_id).where(
                        AgentConversation.super_agent_member_id.in_(gone)
                    )
                )
            ).scalars().all()
        )
        removable = [member_id for member_id in gone if member_id not in bound]
        if removable:
            await session.execute(
                sql_delete(SuperAgentMember).where(SuperAgentMember.id.in_(removable))
            )
        for member_id in bound:
            row = old.get(member_id)
            if row is not None:
                row.is_active = False
    await session.commit()
    await session.refresh(cfg)
    return await _cfg_dict(session, cfg)


async def async_delete(params: dict) -> None:
    """删除超级智能体配置。

        参数：super_agent_id / session / user_id。
        """
    session: AsyncSession = params["session"]
    cfg = await _get_cfg(session, params["user_id"], params.get("super_agent_id"))
    if cfg is None:
        raise ApiError("超级智能体不存在", code=404)
    await session.execute(
        sql_delete(SuperAgentMember).where(SuperAgentMember.super_agent_id == cfg.id)
    )
    await session.delete(cfg)
    await session.commit()


async def async_enabled(params: dict) -> dict | None:
    """返回已启用且可用的超级智能体。

        参数：super_agent_id / session / user_id。
        """
    session: AsyncSession = params["session"]
    cfg = await _get_cfg(session, params["user_id"], params.get("super_agent_id"))
    if cfg is None or not cfg.enabled:
        return None
    members = await _members(session, cfg.id)
    if not any(row.role == "main" and row.is_active for row in members):
        return None
    return await _cfg_dict(session, cfg)


async def async_resolve_member(params: dict) -> dict | None:
    """返回成员 + 可直接覆盖到用户配置上的 llm/prompt。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    cfg = await _get_cfg(session, user.id, params.get("super_agent_id"))
    if cfg is None:
        return None
    members = await _members(session, cfg.id)
    member = None
    if params.get("member_id"):
        member = next((row for row in members if row.id == params["member_id"]), None)
        if member is not None and not member.is_active:
            member = None
    if member is None:
        role = params.get("role") or "main"
        member = next(
            (row for row in members if row.role == role and row.is_active), None
        )
    if member is None:
        member = next(
            (row for row in members if row.role == "main" and row.is_active), None
        )
    if member is None:
        return None
    base = await async_effective({"session": session, "user": user})
    overrides = {key: value for key, value in _load(member.llm_config).items()
                 if key in LLM_FIELDS and value not in (None, "")}
    base.update(overrides)
    if member.system_prompt:
        base["system_prompt"] = member.system_prompt
    roster = [
        {"id": row.id, "name": row.name, "role": row.role, "description": row.description}
        for row in members if row.is_active
    ]
    return {
        "config": base,
        "member": _member_dict(member),
        "super_agent": {
            "id": cfg.id,
            "name": cfg.name,
            "member_id": member.id,
            "member_name": member.name,
            "role": member.role,
        },
        "roster": roster,
    }


async def async_create_conversation(params: dict) -> dict:
    """创建超级智能体成员会话。

        参数：super_agent_id / member_id / role / title / parent_conversation_id / session / user_id。
        """
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    cfg = await _get_cfg(session, user_id, params.get("super_agent_id"))
    if cfg is None or not cfg.enabled:
        raise ApiError("超级智能体未启用")
    members = await _members(session, cfg.id)
    member = None
    if params.get("member_id"):
        member = next((row for row in members if row.id == params["member_id"]), None)
    if member is None:
        member = next(
            (row for row in members if row.role == (params.get("role") or "main") and row.is_active),
            None,
        )
    if member is None:
        raise ApiError("超级智能体没有可用成员")
    title = str(params.get("title") or member.name)[:200]
    row = AgentConversation(
        user_id=user_id,
        title=title,
        origin="super_main" if member.role == "main" else "super_sub",
        super_agent_id=cfg.id,
        super_agent_member_id=member.id,
        parent_conversation_id=params.get("parent_conversation_id"),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": row.id,
        "title": row.title,
        "origin": row.origin,
        "super_agent_id": row.super_agent_id,
        "super_agent_member_id": row.super_agent_member_id,
        "member_name": member.name,
        "member_role": member.role,
    }
