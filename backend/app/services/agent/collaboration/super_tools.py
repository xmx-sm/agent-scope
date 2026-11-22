"""超级智能体主会话的会话编排工具。"""

from __future__ import annotations

import asyncio
import json

from agentscope.tool import FunctionTool
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import AgentConversation, AgentMessage
from app.services.agent.collaboration.super_agent import async_create_conversation


def build_super_group(user_id: str, super_ctx: dict) -> list:
    agent_id = str(super_ctx.get("super_agent_id") or "")
    self_cid = str(super_ctx.get("conversation_id") or "")
    roster = super_ctx.get("roster") or []
    roster_text = "、".join(
        f"{row.get('name')}（{'主' if row.get('role') == 'main' else '子'}"
        f"{('：' + row['description']) if row.get('description') else ''}）"
        for row in roster
    )

    def err(message: str) -> dict:
        return {"code": 400, "data": None, "message": f"[超级智能体] {message}"}

    async def owned(kind: str = "all", limit: int = 50) -> list[dict]:
        async with AsyncSessionLocal() as session:
            rows = list(
                (
                    await session.execute(
                        select(AgentConversation)
                        .where(
                            AgentConversation.user_id == user_id,
                            AgentConversation.super_agent_id == agent_id,
                        )
                        .order_by(AgentConversation.updated_at.desc())
                        .limit(limit)
                    )
                ).scalars().all()
            )
            if kind == "main":
                rows = [row for row in rows if row.origin == "super_main"]
            elif kind == "sub":
                rows = [row for row in rows if row.origin == "super_sub"]
            items = []
            for row in rows:
                last = (
                    await session.execute(
                        select(AgentMessage.content)
                        .where(
                            AgentMessage.conversation_id == row.id,
                            AgentMessage.role == "assistant",
                        )
                        .order_by(AgentMessage.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                items.append(
                    {
                        "conversation_id": row.id,
                        "title": row.title,
                        "origin": row.origin,
                        "member_id": row.super_agent_member_id,
                        "is_self": row.id == self_cid,
                        "last_reply": (last or "")[:200] or None,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                )
            return items

    async def target(conversation_id: str) -> AgentConversation | None:
        if not conversation_id:
            return None
        async with AsyncSessionLocal() as session:
            return (
                await session.execute(
                    select(AgentConversation).where(
                        AgentConversation.id == conversation_id,
                        AgentConversation.user_id == user_id,
                        AgentConversation.super_agent_id == agent_id,
                    )
                )
            ).scalar_one_or_none()

    async def run_turn(conversation_id: str, content: str, timeout: int) -> dict:
        from app.services.agent.conversation.chat import async_run_turn

        async def collect() -> dict:
            return await async_run_turn(
                user_id, conversation_id, content,
                super_depth=int(super_ctx.get("depth") or 0) + 1,
            )

        task = asyncio.create_task(collect())
        try:
            done, _pending = await asyncio.wait({task}, timeout=timeout)
        except asyncio.CancelledError:
            task.cancel()
            raise
        if not done:
            return {
                "code": 200,
                "submitted": True,
                "content": None,
                "message": "该轮仍在后台生成，稍后用 read 查看结果，不要重复下发",
            }
        return task.result()

    async def super_conversation(**kwargs) -> dict:
        data = dict(kwargs.get("args") or {}) if isinstance(kwargs.get("args"), dict) else {}
        for key, value in kwargs.items():
            if key != "args":
                data.setdefault(key, value)
        function = str(data.get("function") or "").strip()

        if function == "list":
            kind = str(data.get("kind") or "all").lower()
            if kind not in ("all", "main", "sub"):
                return err("kind 只支持 all/main/sub")
            items = await owned(kind)
            return {"code": 200, "data": {"count": len(items), "conversations": items},
                    "message": "success"}

        if function == "read":
            cid = str(data.get("conversation_id") or "")
            if not await target(cid):
                return err("会话不存在或不属于当前超级智能体")
            limit = max(1, min(int(data.get("limit") or 20), 100))
            async with AsyncSessionLocal() as session:
                rows = list(
                    (
                        await session.execute(
                            select(AgentMessage)
                            .where(AgentMessage.conversation_id == cid)
                            .order_by(AgentMessage.created_at.desc())
                            .limit(limit)
                        )
                    ).scalars().all()
                )
            rows.reverse()
            return {
                "code": 200,
                "data": {
                    "conversation_id": cid,
                    "messages": [
                        {"role": row.role, "content": row.content[:2000],
                         "created_at": row.created_at.isoformat() if row.created_at else None}
                        for row in rows
                    ],
                },
                "message": "success",
            }

        if function == "create":
            title = str(data.get("title") or "").strip()
            if not title:
                return err("title 不能为空")
            member_name = str(data.get("member") or "").strip()
            member = next((row for row in roster if row.get("name") == member_name), None) \
                if member_name else None
            if member_name and member is None:
                return err(f"角色 {member_name} 不存在，可用：{roster_text}")
            async with AsyncSessionLocal() as session:
                conv = await async_create_conversation(
                    {
                        "session": session,
                        "user_id": user_id,
                        "super_agent_id": agent_id,
                        "member_id": member.get("id") if member else None,
                        "title": title,
                        "parent_conversation_id": self_cid,
                    }
                )
            out = {
                "conversation_id": conv["id"],
                "title": conv["title"],
                "member": member_name or roster_text.split("（", 1)[0],
            }
            content = str(data.get("content") or "").strip()
            if content:
                reply = await run_turn(conv["id"], content, 300)
                out["reply"] = reply
                return {"code": reply.get("code") or 200, "data": out,
                        "message": reply.get("message") or "success"}
            return {"code": 200, "data": out, "message": f"会话已创建：{title}"}

        if function == "send":
            cid = str(data.get("conversation_id") or "")
            content = str(data.get("content") or "").strip()
            if not content:
                return err("content 不能为空")
            if cid == self_cid:
                return err("不能向自己当前这轮会话下发任务")
            if not await target(cid):
                return err("会话不存在或不属于当前超级智能体")
            timeout = max(5, min(int(data.get("timeout") or 300), 600))
            reply = await run_turn(cid, content, timeout)
            return {"code": reply.get("code") or 200,
                    "data": {"conversation_id": cid, **reply},
                    "message": reply.get("message") or "success"}

        if function == "rename":
            cid = str(data.get("conversation_id") or "")
            title = str(data.get("title") or "").strip()
            if not title:
                return err("title 不能为空")
            if not await target(cid):
                return err("会话不存在或不属于当前超级智能体")
            async with AsyncSessionLocal() as session:
                row = await session.get(AgentConversation, cid)
                row.title = title[:200]
                await session.commit()
            return {"code": 200, "data": {"conversation_id": cid, "title": title},
                    "message": "success"}

        if function == "delete":
            cid = str(data.get("conversation_id") or "")
            if cid == self_cid:
                return err("不能删除自己当前所在的会话")
            if not await target(cid):
                return err("会话不存在或不属于当前超级智能体")
            async with AsyncSessionLocal() as session:
                row = await session.get(AgentConversation, cid)
                await session.delete(row)
                await session.commit()
            return {"code": 200, "data": {"conversation_id": cid}, "message": "已删除"}

        return err(f"未知 function：{function or '(空)'}")

    tool = FunctionTool(
        super_conversation,
        name="super_conversation",
        description=(
            "超级智能体对话编排：列出、创建、重命名、删除本超级智能体名下的会话，"
            "向成员会话下发任务并同步取回回复。可用角色：" + (roster_text or "（未配置）")
        ),
        input_schema={
            "type": "object",
            "properties": {
                "function": {
                    "type": "string",
                    "enum": ["list", "read", "create", "send", "rename", "delete"],
                },
                "conversation_id": {"type": "string"},
                "title": {"type": "string"},
                "member": {"type": "string"},
                "content": {"type": "string"},
                "kind": {"type": "string"},
                "limit": {"type": "integer"},
                "timeout": {"type": "integer"},
            },
            "required": ["function"],
            "additionalProperties": True,
        },
        is_concurrency_safe=False,
    )
    from agentscope.tool import ToolGroup

    return [
        ToolGroup(
            name="super",
            description="超级智能体会话编排：创建子会话、派活、读取结果",
            instructions="先用 list 查看会话，再 create/send/read；子会话结果以工具返回为准。",
            tools=[tool],
        )
    ]
