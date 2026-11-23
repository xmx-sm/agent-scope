"""A2A 伙伴管理与互调。"""

from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import A2AInvocation, A2APeer, A2ASessionMap, AgentConversation, User
from app.utils.mask import SENTINEL


def _new_key() -> str:
    """内部辅助函数：_new_key。
    参数：无。
    """
    return "a2a_" + secrets.token_urlsafe(32)


def _load_protocol_config(raw: Any) -> dict:
    """解析非标准协议配置；非法内容回退为空字典。"""
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _public(row: A2APeer) -> dict:
    """内部辅助函数：_public。
    参数：row。
    """
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "endpoint": row.endpoint,
        "remote_name": row.remote_name,
        "direction": row.direction,
        "protocol": row.protocol,
        "protocol_config": _load_protocol_config(row.protocol_config),
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
    """列出当前用户的 A2A 伙伴。

        参数：session / user。
        """
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
    """新建或更新 A2A 伙伴。

        参数：session / user / data。
        """
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
    protocol = str(data.get("protocol") or "lite").strip().lower()
    if protocol == "a2a":
        protocol = "standard"
    if protocol not in ("lite", "standard"):
        raise ApiError("protocol 只支持 lite/standard")

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
    protocol_config = data.get("protocol_config")
    if protocol_config is None:
        protocol_config = {}
    if not isinstance(protocol_config, dict):
        raise ApiError("protocol_config 必须是 JSON 对象")
    row.protocol_config = json.dumps(protocol_config, ensure_ascii=False)
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
    """内部辅助函数：_owned_peer。
    参数：session / user / peer_id。
    """
    row = await session.get(A2APeer, peer_id)
    if row is None or row.owner_user_id != user.id:
        raise ApiError("伙伴不存在", code=404)
    return row


async def async_delete_peer(params: dict) -> None:
    """删除 A2A 伙伴及其会话映射。

        参数：session / user / peer_id。
        """
    session: AsyncSession = params["session"]
    row = await _owned_peer(session, params["user"], params["peer_id"])
    await session.delete(row)
    await session.commit()


async def async_rotate_key(params: dict) -> dict:
    """重置 A2A 伙伴入站密钥。

        参数：session / user / peer_id。
        """
    session: AsyncSession = params["session"]
    row = await _owned_peer(session, params["user"], params["peer_id"])
    row.api_key = _new_key()
    await session.commit()
    return {"peer_id": row.id, "api_key": row.api_key}


async def async_reveal_key(params: dict) -> dict:
    """查看 A2A 伙伴密钥明文。

        参数：session / user / peer_id。
        """
    session: AsyncSession = params["session"]
    row = await _owned_peer(session, params["user"], params["peer_id"])
    return {"peer_id": row.id, "api_key": row.api_key}


async def _count_today(session: AsyncSession, peer_id: str, direction: str) -> int:
    """内部辅助函数：_count_today。
    参数：session / peer_id / direction。
    """
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


def _standard_base_candidates(endpoint: str) -> list[str]:
    """把 endpoint 归一成可能的 A2A 服务根地址（用于拉 Agent Card）。"""
    raw = str(endpoint or "").strip().rstrip("/")
    if not raw:
        return []
    candidates = [raw]
    parts = urlsplit(raw)
    path = parts.path.rstrip("/")
    if path.endswith("/a2a"):
        prefix = path[: -len("/a2a")]
        if prefix:
            candidates.append(
                urlunsplit((parts.scheme, parts.netloc, prefix, "", ""))
            )
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    if origin not in candidates:
        candidates.append(origin)
    return candidates


def _render_template(value: Any, ctx: dict[str, Any]) -> Any:
    """递归替换字典/列表/字符串中的 {message}、{session_hint} 等占位符。"""
    if isinstance(value, str):
        for key, item in ctx.items():
            value = value.replace("{" + key + "}", str(item))
        return value
    if isinstance(value, list):
        return [_render_template(item, ctx) for item in value]
    if isinstance(value, dict):
        return {key: _render_template(item, ctx) for key, item in value.items()}
    return value


def _pick_path(payload: Any, path: str | None, default: Any = None) -> Any:
    """按 ``data.content`` 这样的点路径读取响应字段。"""
    if not path:
        return default
    current = payload
    for part in str(path).split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return default
        if current is None:
            return default
    return current


def _lite_config(row: A2APeer) -> dict[str, Any]:
    """非标准协议请求字典；未配置时沿用旧 A2A Lite 默认值。"""
    cfg = _load_protocol_config(row.protocol_config)
    return {
        "method": str(cfg.get("method") or "POST").upper(),
        "path": str(cfg.get("path") or "/a2a/invoke"),
        "headers": cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {},
        "body": (
            cfg.get("body")
            if isinstance(cfg.get("body"), dict)
            else cfg.get("json")
            if isinstance(cfg.get("json"), dict)
            else {
                "agent_name": "{remote_name}",
                "message": "{message}",
                "session_hint": "{session_hint}",
            }
        ),
        "response_content_path": str(cfg.get("response_content_path") or "data.content"),
        "response_conversation_path": str(
            cfg.get("response_conversation_path") or "data.conversation_id"
        ),
        "response_task_path": str(cfg.get("response_task_path") or ""),
        "test_method": str(cfg.get("test_method") or "GET").upper(),
        "test_path": str(cfg.get("test_path") or "/a2a/agents"),
    }


async def _invoke_lite_peer(row: A2APeer, message: str, session_hint: str) -> dict:
    """按 protocol_config 字典调用非标准 A2A 伙伴。"""
    cfg = _lite_config(row)
    ctx = {
        "message": message,
        "session_hint": session_hint,
        "peer_name": row.name,
        "remote_name": row.remote_name or row.name,
        "api_key": row.api_key,
        "endpoint": row.endpoint,
    }
    path = str(_render_template(cfg["path"], ctx))
    url = (
        path
        if path.startswith(("http://", "https://"))
        else row.endpoint.rstrip("/") + "/" + path.lstrip("/")
    )
    headers = {"X-Api-Key": row.api_key}
    headers.update(
        {
            str(key): str(value)
            for key, value in (_render_template(cfg["headers"], ctx) or {}).items()
        }
    )
    body = _render_template(cfg["body"], ctx)
    method = str(cfg["method"] or "POST").upper()
    async with httpx.AsyncClient(timeout=row.timeout_seconds) as client:
        if method in ("GET", "HEAD"):
            resp = await client.request(method, url, headers=headers, params=body)
        else:
            resp = await client.request(method, url, headers=headers, json=body)
        resp.raise_for_status()
        payload = resp.json()
    content = _pick_path(payload, cfg["response_content_path"])
    if content is None:
        data = payload.get("data") if isinstance(payload, dict) else payload
        content = data.get("content") if isinstance(data, dict) else ""
    return {
        "content": str(content or ""),
        "conversation_id": _pick_path(payload, cfg["response_conversation_path"]),
        "task_id": _pick_path(payload, cfg["response_task_path"]),
    }


async def _invoke_standard_peer(row: A2APeer, message: str) -> dict:
    """用 AgentScope ``A2AAgent`` 调用标准 A2A 1.0 伙伴。"""
    try:
        from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
        from a2a.client.auth import AuthInterceptor, CredentialService
        from a2a.utils.constants import TransportProtocol
        from agentscope.agent import A2AAgent
        from agentscope.message import UserMsg
    except ImportError as exc:
        raise ApiError(
            "未安装标准 A2A 依赖，请安装 backend/requirements-a2a.txt 后重试"
        ) from exc

    class _StaticCredentialService(CredentialService):
        async def get_credentials(self, security_scheme_name: str, context):
            return row.api_key

    timeout = min(float(row.timeout_seconds or 120), 300)
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout) as http:
        card = None
        for base in _standard_base_candidates(row.endpoint):
            try:
                card = await A2ACardResolver(http, base).get_agent_card()
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if card is None:
            raise ApiError(f"无法获取 A2A Agent Card：{last_error}")

        factory = ClientFactory(
            ClientConfig(
                streaming=True,
                polling=False,
                httpx_client=http,
                supported_protocol_bindings=[TransportProtocol.JSONRPC],
            )
        )
        client = factory.create(
            card,
            interceptors=[AuthInterceptor(_StaticCredentialService())],
        )
        adapter = A2AAgent(card, client=client)
        try:
            reply = await adapter.reply(UserMsg("user", message))
        finally:
            await adapter.aclose()
        text = ""
        if hasattr(reply, "get_text_content"):
            try:
                text = reply.get_text_content() or ""
            except Exception:
                text = ""
        if not text:
            text = str(getattr(reply, "content", "") or "")
        return {
            "content": text,
            "conversation_id": adapter.state.context_id,
            "task_id": adapter.state.task_id,
        }


async def async_test_peer(params: dict) -> dict:
    """测试 A2A 伙伴连通性。

        参数：session / user / peer_id。
        """
    session: AsyncSession = params["session"]
    row = await _owned_peer(session, params["user"], params["peer_id"])
    if not row.endpoint:
        raise ApiError("该伙伴没有配置 endpoint")
    if not row.api_key:
        raise ApiError("该伙伴没有配置 API Key")
    if str(row.protocol or "lite").lower() in ("standard", "a2a"):
        try:
            from a2a.client import A2ACardResolver
            from google.protobuf.json_format import MessageToDict
        except ImportError as exc:
            raise ApiError(
                "未安装标准 A2A 依赖，请安装 backend/requirements-a2a.txt 后重试"
            ) from exc

        last_error: Exception | None = None
        try:
            async with httpx.AsyncClient(timeout=min(row.timeout_seconds, 30)) as client:
                for base in _standard_base_candidates(row.endpoint):
                    try:
                        card = await A2ACardResolver(client, base).get_agent_card()
                        return {
                            "peer_id": row.id,
                            "endpoint": base,
                            "protocol": "standard",
                            "response": MessageToDict(
                                card,
                                preserving_proto_field_name=False,
                            ),
                        }
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        raise ApiError(f"连接失败：{last_error}")

    cfg = _lite_config(row)
    path = str(cfg["test_path"] or "/a2a/agents")
    url = (
        path
        if path.startswith(("http://", "https://"))
        else row.endpoint.rstrip("/") + "/" + path.lstrip("/")
    )
    try:
        async with httpx.AsyncClient(timeout=min(row.timeout_seconds, 30)) as client:
            resp = await client.request(
                str(cfg["test_method"] or "GET"),
                url,
                headers={"X-Api-Key": row.api_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(f"连接失败：{exc}") from exc
    return {"peer_id": row.id, "endpoint": url, "response": data}


async def async_invoke_peer(params: dict) -> dict:
    """出站调用 A2A 伙伴。

        参数：peer / message / session_hint / session / user。
        """
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

    if str(row.protocol or "lite").lower() in ("standard", "a2a"):
        started = time.monotonic()
        try:
            result = await _invoke_standard_peer(row, message)
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
        content = str(result.get("content") or "")
        elapsed = int((time.monotonic() - started) * 1000)
        session.add(
            A2AInvocation(
                peer_id=row.id, direction="out", status="ok", prompt=message,
                response=content[:4000], elapsed_ms=elapsed,
                conversation_id=result.get("conversation_id"),
            )
        )
        await session.commit()
        return {
            "peer": row.name,
            "content": content,
            "conversation_id": result.get("conversation_id"),
            "task_id": result.get("task_id"),
            "protocol": "standard",
        }

    started = time.monotonic()
    session_hint = str(params.get("session_hint") or "default")[:200]
    try:
        result = await _invoke_lite_peer(row, message, session_hint)
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
    content = str(result.get("content") or "")
    elapsed = int((time.monotonic() - started) * 1000)
    session.add(
        A2AInvocation(
            peer_id=row.id, direction="out", status="ok", prompt=message,
            response=content[:4000], elapsed_ms=elapsed,
            conversation_id=result.get("conversation_id"),
        )
    )
    await session.commit()
    return {
        "peer": row.name,
        "content": content,
        "conversation_id": result.get("conversation_id"),
        "task_id": result.get("task_id"),
        "protocol": "lite",
    }


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
    """列出 A2A 协作记忆。

        参数：session / user。
        """
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
    """清除一条 A2A 协作记忆。

        参数：session / user / session_id。
        """
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
    """列出 A2A 调用留痕。

        参数：session / user。
        """
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


async def resolve_inbound_peer(params: dict) -> A2APeer | None:
    """按 X-Api-Key 解析入站伙伴。参数：session / api_key。"""
    session: AsyncSession = params["session"]
    api_key: str = params["api_key"]
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


async def inbound_catalog(params: dict) -> dict:
    """返回入站伙伴的 Agent 目录。参数：peer。"""
    peer: A2APeer = params["peer"]
    return {
        "name": peer.name,
        "description": peer.description or "Agent Scope A2A 智能体",
        "tools_enabled": peer.allow_tools,
        "protocols": ["a2a-lite"],
        "max_calls_per_day": peer.max_calls_per_day,
    }


async def resolve_inbound_session(params: dict) -> str:
    """按伙伴 + session_hint 复用或创建入站会话。参数：session / peer / session_hint。"""
    session: AsyncSession = params["session"]
    peer: A2APeer = params["peer"]
    hint = (params.get("session_hint") or "default")[:200]
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
    """处理入站 A2A 调用。

        参数：api_key / session / body。
        """
    session: AsyncSession = params["session"]
    api_key = str(params.get("api_key") or "")
    body = params["body"]
    peer = await resolve_inbound_peer({"session": session, "api_key": api_key})
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
    cid = await resolve_inbound_session({"session": session, "peer": peer, "session_hint": body.session_hint})
    started = time.monotonic()
    try:
        from app.services.agent.conversation.chat import async_run_turn

        result = await async_run_turn(
            {
                "user_id": peer.owner_user_id,
                "conversation_id": cid,
                "content": body.message,
                "super_depth": 1,
                "tools_enabled": peer.allow_tools,
            }
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
