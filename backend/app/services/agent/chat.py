"""Agent 流式对话。"""

from __future__ import annotations

import json
from typing import AsyncGenerator

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import AgentConversation, AgentMessage, User
from app.services.agent.conversations import async_get_owned, async_save_message
from app.services.agent.scope_bridge import ROOT  # noqa: F401 确保 scope 路径已注入
from app.services.agent.toolkit import async_build_toolkit
from app.services.agent.user_config import async_effective
from app.services.security.prompt import async_build_security_prompt


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _load_llm(session, user: User) -> tuple[dict, str]:
    cfg = await async_effective({"session": session, "user": user})
    model = str(cfg.get("model") or "")
    base_url = str(cfg.get("base_url") or "")
    if not model:
        raise ValueError("请先在 Agent 配置中填写对话模型")
    if not base_url:
        raise ValueError("请先在 Agent 配置中填写模型 API 地址")
    return {
        "provider": str(cfg.get("provider") or "openai-compatible"),
        "model": model,
        "base_url": base_url,
        "api_key": str(cfg.get("api_key") or ""),
        "stream": bool(cfg.get("stream", True)),
        "think": bool(cfg.get("think", False)),
        "thinking_budget": int(cfg.get("thinking_budget", 0) or 0) or None,
        "reasoning_effort": str(cfg.get("reasoning_effort") or "medium"),
        "temperature": float(cfg.get("temperature", 0.7) or 0.7),
        "max_tokens": int(cfg.get("max_tokens", 4096) or 4096),
        "context_size": int(cfg.get("context_window", 131072) or 131072),
    }, str(cfg.get("system_prompt") or "")


async def _history_text(session, conversation_id: str, limit: int = 20) -> str:
    rows = (
        await session.execute(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conversation_id)
            .order_by(AgentMessage.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    rows = list(reversed(rows))
    return "\n".join(
        f"{'用户' if row.role == 'user' else '助手'}：{row.content[:1200]}"
        for row in rows
        if row.content
    )


async def async_stream_chat(user_id: str, conversation_id: str, content: str) -> AsyncGenerator[str, None]:
    """SSE 生成器：自己管理数据库会话，避免依赖释放导致流中断。"""
    from agentscope.message import UserMsg
    from agentscope.event import (
        ModelCallEndEvent,
        ModelCallStartEvent,
        RequireUserConfirmEvent,
        TextBlockDeltaEvent,
        ThinkingBlockDeltaEvent,
        ToolCallStartEvent,
        ToolResultEndEvent,
        ToolResultStartEvent,
        ToolResultTextDeltaEvent,
    )
    from scope.agent.builder import async_get_agent
    from scope.agent.runtime import AgentRuntime

    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            yield _sse("error", {"error": "用户不存在"})
            return
        conv = await session.get(AgentConversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            yield _sse("error", {"error": "会话不存在"})
            return
        history = await _history_text(session, conversation_id)
        await async_save_message(
            session, conversation_id=conversation_id, role="user", content=content
        )
        try:
            llm, user_prompt = await _load_llm(session, user)
            security_prompt = await async_build_security_prompt({"session": session})
            system_prompt = user_prompt or "你是一个企业智能助手。"
            toolkit = await async_build_toolkit({"session": session, "user": user})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"error": str(exc)})
            return

    full_prompt = system_prompt.strip()
    if security_prompt:
        full_prompt += "\n\n" + security_prompt.strip()
    if history:
        full_prompt += "\n\n[最近对话]\n" + history

    result = await async_get_agent(
        {
            "llm": llm,
            "agent": {
                "name": "assistant",
                "system_prompt": full_prompt,
                "toolkit": toolkit,
            },
        }
    )
    if result.get("code") != 200:
        yield _sse("error", {"error": result.get("message") or "Agent 初始化失败"})
        return

    runtime = AgentRuntime(result["data"]["agent"], default_approval="allow")
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_events: list[dict] = []
    tool_names: dict[str, str] = {}
    tool_args: dict[str, str] = {}
    tool_outputs: dict[str, str] = {}
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_input_tokens": 0}
    model_usage: dict[str, dict] = {}
    current_model = "unknown"

    try:
        async for evt in runtime.reply_stream(UserMsg("user", content)):
            if isinstance(evt, TextBlockDeltaEvent):
                if evt.delta:
                    text_parts.append(evt.delta)
                    yield _sse("text_delta", {"text": evt.delta})
            elif isinstance(evt, ThinkingBlockDeltaEvent):
                if evt.delta:
                    reasoning_parts.append(evt.delta)
                    yield _sse("reasoning_delta", {"text": evt.delta})
            elif isinstance(evt, ToolCallStartEvent):
                tool_names[evt.tool_call_id] = evt.tool_call_name
                tool_args[evt.tool_call_id] = ""
                yield _sse("tool_start", {
                    "tool_call_id": evt.tool_call_id,
                    "tool_name": evt.tool_call_name,
                })
            elif isinstance(evt, ToolResultStartEvent):
                tool_outputs[evt.tool_call_id] = ""
            elif isinstance(evt, ToolResultTextDeltaEvent):
                tool_outputs[evt.tool_call_id] = tool_outputs.get(evt.tool_call_id, "") + evt.delta
            elif isinstance(evt, ToolResultEndEvent):
                item = {
                    "tool_call_id": evt.tool_call_id,
                    "name": tool_names.get(evt.tool_call_id, ""),
                    "input": tool_args.get(evt.tool_call_id, ""),
                    "output": tool_outputs.get(evt.tool_call_id, ""),
                    "status": str(getattr(evt, "state", "success")),
                }
                tool_events.append(item)
                yield _sse("tool_result", item)
            elif isinstance(evt, RequireUserConfirmEvent):
                # default_approval=allow：runtime 已自动放行，这里不重复处理
                continue
            elif isinstance(evt, ModelCallStartEvent):
                current_model = getattr(evt, "model_name", None) or "unknown"
            elif isinstance(evt, ModelCallEndEvent):
                input_tokens = getattr(evt, "input_tokens", 0) or 0
                output_tokens = getattr(evt, "output_tokens", 0) or 0
                cache_tokens = getattr(evt, "cache_input_tokens", 0) or 0
                usage["input_tokens"] += input_tokens
                usage["output_tokens"] += output_tokens
                usage["cache_input_tokens"] += cache_tokens
                item = model_usage.setdefault(
                    current_model,
                    {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_input_tokens": 0},
                )
                item["calls"] += 1
                item["input_tokens"] += input_tokens
                item["output_tokens"] += output_tokens
                item["cache_input_tokens"] += cache_tokens
    except Exception as exc:  # noqa: BLE001
        yield _sse("error", {"error": f"生成失败：{exc}"})
        return

    final_text = "".join(text_parts).strip()
    async with AsyncSessionLocal() as session:
        assistant = await async_save_message(
            session,
            conversation_id=conversation_id,
            role="assistant",
            content=final_text,
            reasoning="".join(reasoning_parts),
            tool_events=json.dumps(tool_events, ensure_ascii=False),
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_input_tokens=usage["cache_input_tokens"],
        )
        if model_usage:
            from app.models import AgentModelCall

            for model_name, item in model_usage.items():
                session.add(
                    AgentModelCall(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        message_id=assistant.id,
                        source="web",
                        model_name=model_name,
                        calls=item["calls"],
                        input_tokens=item["input_tokens"],
                        output_tokens=item["output_tokens"],
                        cache_input_tokens=item["cache_input_tokens"],
                    )
                )
            await session.commit()
    yield _sse("done", {
        "conversation_id": conversation_id,
        "message_id": assistant.id,
        "content": final_text,
    })
