"""用户子智能体管理。"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.tools import all_items
from app.models import User, UserSubagent
from app.services.access.tools.evaluate import async_tool_view
from app.services.agent.config.user_config import async_effective
from app.utils.mask import SENTINEL, mask_secret

_ALLOWED = {item["tool"] for item in all_items()}
LLM_FIELDS = (
    "provider", "base_url", "api_key", "model", "temperature", "max_tokens",
    "context_window", "stream", "think", "thinking_budget", "reasoning_effort",
)


def _load(raw) -> dict:
    """解析 JSON 对象；非法内容返回空对象。"""
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _clean_llm(raw) -> dict:
    """只保留模型相关字段，去掉空值。"""
    if not isinstance(raw, dict):
        return {}
    return {
        key: value for key, value in raw.items()
        if key in LLM_FIELDS and value not in (None, "")
    }


def _public(row: UserSubagent) -> dict:
    """内部辅助函数：_public。
    参数：row。
    """
    llm = _load(row.llm_config)
    if llm.get("api_key"):
        llm["api_key"] = mask_secret(llm["api_key"])
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "system_prompt": row.system_prompt,
        "llm_config": llm,
        "tools": json.loads(row.tools or "[]"),
        "mode": row.mode,
        "is_active": row.is_active,
    }


async def async_list(params: dict) -> list[dict]:
    """列出用户子智能体。

        参数：session / user。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserSubagent).where(UserSubagent.user_id == user.id).order_by(UserSubagent.name)
        )
    ).scalars().all()
    return [_public(row) for row in rows]


async def async_save(params: dict) -> dict:
    """新建或更新子智能体。

        参数：session / user / data。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    data: dict = params["data"]
    name = str(data.get("name") or "").strip()
    if not name:
        raise ApiError("子智能体名称不能为空")
    if not str(data.get("system_prompt") or "").strip():
        raise ApiError("子智能体必须填写系统提示词")
    tools = [str(item) for item in (data.get("tools") or []) if str(item) in _ALLOWED]
    row = None
    if data.get("id"):
        row = await session.get(UserSubagent, data["id"])
        if row is None or row.user_id != user.id:
            raise ApiError("子智能体不存在", code=404)
    else:
        row = (
            await session.execute(
                select(UserSubagent).where(
                    UserSubagent.user_id == user.id, UserSubagent.name == name
                )
            )
        ).scalar_one_or_none()
    if row is None:
        row = UserSubagent(user_id=user.id, name=name)
        session.add(row)
    row.name = name
    row.description = str(data.get("description") or "")[:500]
    row.system_prompt = str(data.get("system_prompt") or "")
    if "llm_config" in data:
        incoming = data.get("llm_config") or {}
        if not incoming:
            # 前端提交空对象表示清空模型覆盖，回落到个人 Agent 配置
            row.llm_config = "{}"
        else:
            previous = _load(row.llm_config)
            merged = dict(previous)
            for key in LLM_FIELDS:
                if key not in incoming:
                    continue
                value = incoming[key]
                if key == "api_key" and (value == SENTINEL or value == ""):
                    continue
                merged[key] = value
            row.llm_config = json.dumps(merged, ensure_ascii=False)
    row.tools = json.dumps(tools, ensure_ascii=False)
    row.mode = str(data.get("mode") or "auto")
    row.is_active = bool(data.get("is_active", True))
    await session.commit()
    await session.refresh(row)
    return _public(row)


async def async_delete(params: dict) -> None:
    """删除子智能体。

        参数：session / user / subagent_id。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    row = await session.get(UserSubagent, params["subagent_id"])
    if row is None or row.user_id != user.id:
        raise ApiError("子智能体不存在", code=404)
    await session.delete(row)
    await session.commit()


async def async_specs(params: dict) -> list[dict]:
    """返回可用于 scope 委派的 spec 列表，工具按用户有效权限过滤。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserSubagent).where(
                UserSubagent.user_id == user.id, UserSubagent.is_active.is_(True)
            )
        )
    ).scalars().all()
    if not rows:
        return []
    view = await async_tool_view({"session": session, "user": user})
    enabled = {
        tool["name"]
        for group in view["groups"]
        for tool in group["tools"]
        if tool["enabled"]
    }
    base = await async_effective({"session": session, "user": user})
    base_llm = {
        key: base.get(key) for key in LLM_FIELDS
        if base.get(key) not in (None, "")
    }
    result = []
    for row in rows:
        tools = [name for name in json.loads(row.tools or "[]") if name in enabled]
        overrides = _clean_llm(_load(row.llm_config))
        spec = {
            "name": row.name,
            "description": row.description,
            "system_prompt": row.system_prompt,
            "tools": tools,
            "mode": row.mode,
        }
        # 子智能体配置了模型覆盖时，与个人 Agent 配置合并；未配置则交给 default_llm。
        if overrides:
            spec["llm"] = {**base_llm, **overrides}
        result.append(spec)
    return result
