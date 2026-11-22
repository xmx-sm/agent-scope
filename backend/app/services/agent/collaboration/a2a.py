"""A2A 伙伴管理与互调。"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import A2AInvocation, A2APeer, A2ASessionMap, AgentConversation, User
from app.utils.mask import SENTINEL


def _new_key() -> str:
    return "a2a_" + secrets.token_urlsafe(32)


def _public(row: A2APeer) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "endpoint": row.endpoint,
        "remote_name": row.remote_name,
        "direction": row.direction,
        "protocol": row.protocol,
        "allow_tools": row.allow_tools,
        "max_calls_per_day": row.max_calls_per_day,
        "timeout_seconds": row.timeout_seconds,
        "is_active": row.is_active,
        "has_key": bool(row.api_key),
        "api_key": SENTINEL if row.api_key else "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def async_list_peers(params: dict) -> list[dict]:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(A2APeer)
            .where(A2APeer.owner_user_id == user.id)
            .order_by(A2APeer.created_at)
        )
    ).scalars().all()
    return [_public(row) for row in rows]


async def async_save_peer(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    data: dict = params["data"]
    name = str(data.get("name") or "").strip()
    if not name:
        raise ApiError("伙伴名称不能为空")
    direction = str(data.get("direction") or "outbound")
    if direction not in ("outbound", "inbound", "both"):
        raise ApiError("direction 只支持 outbound/inbound/both")
    endpoint = str(data.get("endpoint") or "").strip().rstrip("/")
    if direction in ("outbound", "both") and not endpoint:
        raise ApiError("出站/双向伙伴必须填写 endpoint")
    if endpoint and not endpoint.startswith(("http://", "https://")):
        raise ApiError("endpoint 必须是 http(s) 地址")
    for suffix in ("/a2a/invoke", "/a2a/agents"):
        if endpoint.endswith(suffix):
            endpoint = endpoint[: -len(suffix)].rstrip("/")
    protocol = str(data.get("protocol") or "lite")
    if protocol not in ("lite", "standard"):
        raise ApiError("protocol 只支持 lite/standard（当前实际调用 lite）")

    row = None
    if data.get("id"):
        row = await session.get(A2APeer, data["id"])
        if row is None or row.owner_user_id != user.id:
            raise ApiError("伙伴不存在", code=404)
    else:
        exists = (
            await session.execute(
                select(A2APeer).where(
                    A2APeer.owner_user_id == user.id, A2APeer.name == name
                )
            )
        ).scalar_one_or_none()
        if exists:
            raise ApiError("伙伴名称已存在")
        row = A2APeer(owner_user_id=user.id, name=name, api_key=_new_key())
        session.add(row)
    row.name = name
    row.description = str(data.get("description") or "")[:500]
    row.endpoint = endpoint[:500]
    row.remote_name = str(data.get("remote_name") or "")[:100]
    row.direction = direction
    row.protocol = protocol
    row.allow_tools = bool(data.get("allow_tools"))
    row.max_calls_per_day = max(1, min(int(data.get("max_calls_per_day") or 50), 10000))
    row.timeout_seconds = max(5, min(int(data.get("timeout_seconds") or 120), 300))
    row.is_active = bool(data.get("is_active", True))
    supplied = str(data.get("api_key") or "")
    if supplied and supplied != SENTINEL:
        row.api_key = supplied
    await session.commit()
    await session.refresh(row)
    item = _public(row)
    if not data.get("id"):
        item["api_key_plaintext"] = row.api_key
    return item


async def _owned_peer(session: AsyncSession, user: User, peer_id: str) -> A2APeer:
    row = await session.get(A2APeer, peer_id)
    if row is None or row.owner_user_id != user.id:
        raise ApiError("伙伴不存在", code=404)
    return row


async def async_delete_peer(params: dict) -> None:
    session: AsyncSession = params["session"]
    row = await _owned_peer(session, params["user"], params["peer_id"])
    await session.delete(row)
    await session.commit()


async def async_rotate_key(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = await _owned_peer(session, params["user"], params["peer_id"])
    row.api_key = _new_key()
    await session.commit()
    return {"peer_id": row.id, "api_key": row.api_key}


async def async_reveal_key(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = await _owned_peer(session, params["user"], params["peer_id"])
    return {"peer_id": row.id, "api_key": row.api_key}


async def _count_today(session: AsyncSession, peer_id: str, direction: str) -> int:
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(A2AInvocation)
                .where(
                    A2AInvocation.peer_id == peer_id,
                    A2AInvocation.direction == direction,
                    A2AInvocation.created_at >= day_start,
                )
            )
        ).scalar_one()
    )


async def async_test_peer(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = await _owned_peer(session, params["user"], params["peer_id"])
    if not row.endpoint:
        raise ApiError("该伙伴没有配置 endpoint")
    if not row.api_key:
        raise ApiError("该伙伴没有配置 API Key")
    url = row.endpoint.rstrip("/") + "/a2a/agents"
    try:
        async with httpx.AsyncClient(timeout=min(row.timeout_seconds, 30)) as client:
            resp = await client.get(url, headers={"X-Api-Key": row.api_key})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(f"连接失败：{exc}") from exc
    return {"peer_id": row.id, "endpoint": url, "response": data}


async def async_invoke_peer(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    name = str(params.get("peer") or "").strip()
    message = str(params.get("message") or "").strip()
    if not message:
        raise ApiError("message 不能为空")
    row = (
        await session.execute(
            select(A2APeer).where(
                A2APeer.owner_user_id == user.id, A2APeer.name == name
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError("伙伴不存在", code=404)
    if not row.is_active or row.direction not in ("outbound", "both"):
        raise ApiError("该伙伴未启用出站或已停用")
    if not row.endpoint:
        raise ApiError("该伙伴没有配置 endpoint")
    if not row.api_key:
        raise ApiError("该伙伴没有配置 API Key")
    if await _count_today(session, row.id, "out") >= row.max_calls_per_day:
        raise ApiError("该伙伴今日调用额度已用完", code=429)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=row.timeout_seconds) as client:
            resp = await client.post(
                row.endpoint.rstrip("/") + "/a2a/invoke",
                headers={"X-Api-Key": row.api_key},
                json={
                    "agent_name": row.remote_name or row.name,
                    "message": message,
                    "session_hint": str(params.get("session_hint") or "default")[:200],
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        elapsed = int((time.monotonic() - started) * 1000)
        session.add(
            A2AInvocation(
                peer_id=row.id, direction="out", status="error", prompt=message,
                response=str(exc)[:2000], elapsed_ms=elapsed,
            )
        )
        await session.commit()
        raise ApiError(f"调用伙伴失败：{exc}") from exc
    data = payload.get("data") or payload
    content = str(data.get("content") or "")
    elapsed = int((time.monotonic() - started) * 1000)
    session.add(
        A2AInvocation(
            peer_id=row.id, direction="out", status="ok", prompt=message,
            response=content[:4000], elapsed_ms=elapsed,
            conversation_id=data.get("conversation_id"),
        )
    )
    await session.commit()
    return {"peer": row.name, "content": content, "conversation_id": data.get("conversation_id")}


async def async_peer_specs(params: dict) -> list[dict]:
    """可用于动态挂载独立工具的出站伙伴。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(A2APeer).where(
                A2APeer.owner_user_id == user.id,
                A2APeer.is_active.is_(True),
                A2APeer.direction.in_(("outbound", "both")),
            ).order_by(A2APeer.name)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "remote_name": row.remote_name or row.name,
            "has_endpoint": bool(row.endpoint),
        }
        for row in rows if row.endpoint
    ]


async def async_invoke_peer_by_name(params: dict) -> dict:
    """按伙伴名调用，工具侧使用独立数据库会话。"""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        user = await session.get(User, params["user_id"])
        if user is None:
            raise ApiError("用户不存在", code=404)
        return await async_invoke_peer(
            {
                "session": session,
                "user": user,
                "peer": params["peer"],
                "message": params["message"],
                "session_hint": params.get("session_hint") or "default",
            }
        )


async def async_sessions(params: dict) -> list[dict]:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(A2ASessionMap, A2APeer)
            .join(A2APeer, A2APeer.id == A2ASessionMap.peer_id)
            .where(A2APeer.owner_user_id == user.id)
            .order_by(A2ASessionMap.created_at.desc())
            .limit(200)
        )
    ).all()
    result = []
    for mapping, peer in rows:
        conv = await session.get(AgentConversation, mapping.conversation_id)
        last = ""
        if conv is not None:
            from app.models import AgentMessage

            last = str(
                (
                    await session.execute(
                        select(AgentMessage.content)
                        .where(
                            AgentMessage.conversation_id == conv.id,
                            AgentMessage.role == "assistant",
                        )
                        .order_by(AgentMessage.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                or ""
            )[:200]
        result.append(
            {
                "id": mapping.id,
                "peer_id": mapping.peer_id,
                "peer_name": peer.name,
                "session_hint": mapping.session_hint,
                "conversation_id": mapping.conversation_id,
                "conversation_title": conv.title if conv else None,
                "last_reply": last or None,
                "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
            }
        )
    return result


async def async_forget_session(params: dict) -> None:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    row = await session.get(A2ASessionMap, params["session_id"])
    if row is None:
        raise ApiError("协作记忆不存在", code=404)
    peer = await session.get(A2APeer, row.peer_id)
    if peer is None or peer.owner_user_id != user.id:
        raise ApiError("无权删除该协作记忆", code=403)
    await session.delete(row)
    await session.commit()


async def async_invocations(params: dict) -> list[dict]:
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(A2AInvocation, A2APeer.name)
            .join(A2APeer, A2APeer.id == A2AInvocation.peer_id)
            .where(A2APeer.owner_user_id == user.id)
            .order_by(A2AInvocation.created_at.desc())
            .limit(200)
        )
    ).all()
    return [
        {
            "id": inv.id,
            "peer_name": name,
            "direction": inv.direction,
            "status": inv.status,
            "conversation_id": inv.conversation_id,
            "prompt": inv.prompt,
            "response": inv.response,
            "elapsed_ms": inv.elapsed_ms,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv, name in rows
    ]


# ==================== 入站数据面 ====================


async def resolve_inbound_peer(session: AsyncSession, api_key: str) -> A2APeer | None:
    if not api_key:
        return None
    return (
        await session.execute(
            select(A2APeer).where(
                A2APeer.api_key == api_key,
                A2APeer.is_active.is_(True),
                A2APeer.direction.in_(("inbound", "both")),
            ).order_by(A2APeer.created_at)
        )
    ).scalars().first()


async def inbound_catalog(peer: A2APeer) -> dict:
    return {
        "name": peer.name,
        "description": peer.description or "Agent Scope A2A 智能体",
        "tools_enabled": peer.allow_tools,
        "protocols": ["a2a-lite"],
        "max_calls_per_day": peer.max_calls_per_day,
    }


async def resolve_inbound_session(
    session: AsyncSession, peer: A2APeer, session_hint: str
) -> str:
    hint = (session_hint or "default")[:200]
    mapping = (
        await session.execute(
            select(A2ASessionMap).where(
                A2ASessionMap.peer_id == peer.id,
                A2ASessionMap.session_hint == hint,
            )
        )
    ).scalar_one_or_none()
    if mapping is not None:
        return mapping.conversation_id
    conv = AgentConversation(
        user_id=peer.owner_user_id,
        title=f"A2A · {peer.name} · {hint}"[:200],
        origin="a2a",
    )
    session.add(conv)
    await session.flush()
    session.add(
        A2ASessionMap(peer_id=peer.id, session_hint=hint, conversation_id=conv.id)
    )
    await session.commit()
    return conv.id


async def async_inbound_invoke(params: dict) -> dict:
    session: AsyncSession = params["session"]
    api_key = str(params.get("api_key") or "")
    body = params["body"]
    peer = await resolve_inbound_peer(session, api_key)
    if peer is None:
        raise ApiError("密钥无效或伙伴未启用", code=401)
    if body.agent_name != peer.name:
        raise ApiError(f"未知智能体：{body.agent_name}", code=404)
    if await _count_today(session, peer.id, "in") >= peer.max_calls_per_day:
        session.add(
            A2AInvocation(
                peer_id=peer.id, direction="in", status="quota", prompt=body.message,
                response="今日调用额度已用完",
            )
        )
        await session.commit()
        raise ApiError("今日调用额度已用完", code=429)
    cid = await resolve_inbound_session(session, peer, body.session_hint)
    started = time.monotonic()
    try:
        from app.services.agent.conversation.chat import async_run_turn

        result = await async_run_turn(
            peer.owner_user_id, cid, body.message, super_depth=1,
            tools_enabled=peer.allow_tools,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed = int((time.monotonic() - started) * 1000)
        session.add(
            A2AInvocation(
                peer_id=peer.id, direction="in", status="error", conversation_id=cid,
                prompt=body.message, response=str(exc)[:2000], elapsed_ms=elapsed,
            )
        )
        await session.commit()
        raise ApiError(f"执行失败：{exc}") from exc
    elapsed = int((time.monotonic() - started) * 1000)
    session.add(
        A2AInvocation(
            peer_id=peer.id, direction="in", status="ok", conversation_id=cid,
            prompt=body.message, response=str(result.get("content") or "")[:4000],
            elapsed_ms=elapsed,
        )
    )
    await session.commit()
    return {"content": result.get("content") or "", "conversation_id": cid}


async def async_a2a_tools(params: dict) -> dict:
    """给 AI 使用的 A2A 工具：列出伙伴或调用伙伴。"""
    from app.core.database import AsyncSessionLocal

    if isinstance(params.get("args"), dict):
        params = {**params, **params["args"]}
    function = str(params.get("function") or "list")
    user_id = params.get("user_id") or params.get("_user_id")
    if not user_id:
        return {"code": 401, "data": None, "message": "缺少用户身份"}
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            return {"code": 404, "data": None, "message": "用户不存在"}
        if function == "list":
            rows = await async_list_peers({"session": session, "user": user})
            return {"code": 200, "data": rows, "message": "success"}
        if function == "contexts":
            rows = await async_sessions({"session": session, "user": user})
            return {"code": 200, "data": rows, "message": "success"}
        if function == "invoke":
            result = await async_invoke_peer(
                {
                    "session": session,
                    "user": user,
                    "peer": params.get("peer") or params.get("name") or "",
                    "message": params.get("message") or params.get("content") or "",
                    "session_hint": params.get("session_hint") or "default",
                }
            )
            return {"code": 200, "data": result, "message": "success"}
    return {"code": 400, "data": None, "message": "function 只支持 list/invoke/contexts"}
