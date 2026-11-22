"""Agent 流式对话。"""

from __future__ import annotations

import json
from typing import AsyncGenerator

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import AgentConversation, AgentMessage, User
from app.services.agent.conversation.attachments import async_load_for_model
from app.services.agent.conversation.conversations import async_get_owned, async_save_message
from app.services.agent.runtime.scope_bridge import ROOT  # noqa: F401 确保 scope 路径已注入
from app.services.agent.resources.mcps import async_active_servers
from app.services.agent.resources.skills import async_active_dirs
from app.services.agent.resources.subagents import async_specs as async_subagent_specs
from app.services.agent.runtime.toolkit import async_build_toolkit
from app.services.config.service import async_get_config
from app.services.agent.config.user_config import async_effective
from app.services.access.security.prompt import async_build_security_prompt


def _sse(event: str, data: dict) -> str:
    """内部辅助函数：_sse。
    参数：event / data。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _llm_from_config(cfg: dict) -> dict:
    """内部辅助函数：_llm_from_config。
    参数：cfg。
    """
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
        "video_support": bool(cfg.get("video_support")),
        "video_fps": float(cfg.get("video_fps") or 0) or None,
    }


async def _load_llm(session, user: User, override: dict | None = None) -> tuple[dict, str, bool]:
    """内部辅助函数：_load_llm。
    参数：session / user / override。
    """
    cfg = await async_effective({"session": session, "user": user})
    cfg["video_support"] = bool(
        await async_get_config({"session": session, "key": "ai.video_support", "default": False})
    )
    cfg["video_fps"] = float(
        await async_get_config({"session": session, "key": "ai.video_fps", "default": 0}) or 0
    )
    cfg["video_max_mb"] = int(
        await async_get_config({"session": session, "key": "ai.video_max_mb", "default": 20}) or 20
    )
    if override:
        cfg.update(override)
    model = str(cfg.get("model") or "")
    base_url = str(cfg.get("base_url") or "")
    if not model:
        raise ValueError("请先在 Agent 配置中填写对话模型")
    if not base_url:
        raise ValueError("请先在 Agent 配置中填写模型 API 地址")
    return _llm_from_config(cfg), str(cfg.get("system_prompt") or ""), bool(
        cfg.get("memory_enabled", False)
    )


async def _history_text(session, conversation_id: str, limit: int = 20) -> str:
    """内部辅助函数：_history_text。
    参数：session / conversation_id / limit。
    """
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


async def async_stream_chat(params: dict) -> AsyncGenerator[str, None]:
    """SSE 生成器：自己管理数据库会话，避免依赖释放导致流中断。"""
    user_id = params["user_id"]
    conversation_id = params["conversation_id"]
    content = params.get("content") or ""
    attachment_ids = params.get("attachment_ids") or []
    super_depth = int(params.get("super_depth") or 0)
    tools_enabled = bool(params.get("tools_enabled", True))
    source = str(params.get("source") or "web")
    from agentscope.message import Base64Source, DataBlock, TextBlock, UserMsg
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
        super_ctx = None
        member_override = None
        if conv.super_agent_member_id and conv.super_agent_id:
            from app.services.agent.collaboration.super_agent import async_resolve_member

            resolved = await async_resolve_member(
                {
                    "session": session,
                    "user": user,
                    "super_agent_id": conv.super_agent_id,
                    "member_id": conv.super_agent_member_id,
                }
            )
            if resolved:
                member_override = resolved["config"]
                super_ctx = {
                    **resolved["super_agent"],
                    "conversation_id": conversation_id,
                    "depth": super_depth,
                    "roster": resolved["roster"],
                }
        history = await _history_text(session, conversation_id)
        meta, attachment_text, images, videos = await async_load_for_model(
            {
                "session": session,
                "user_id": user_id,
                "ids": attachment_ids or [],
                "video_support": bool(
                    await async_get_config(
                        {"session": session, "key": "ai.video_support", "default": False}
                    )
                ),
                "video_max_mb": int(
                    await async_get_config(
                        {"session": session, "key": "ai.video_max_mb", "default": 20}
                    ) or 20
                ),
            }
        )
        await async_save_message(
            {
                "session": session,
                "conversation_id": conversation_id,
                "role": "user",
                "content": content,
                "attachments": json.dumps(meta, ensure_ascii=False),
            }
        )
        knowledge_text = ""
        try:
            llm, user_prompt, memory_enabled = await _load_llm(
                session, user, member_override
            )
            security_prompt = await async_build_security_prompt({"session": session})
            system_prompt = user_prompt or "你是一个企业智能助手。"
            knowledge_text = ""
            try:
                from app.services.agent.knowledge import async_search

                found = await async_search(
                    {
                        "session": session,
                        "user_id": user.id,
                        "query": content,
                        "library_ids": [],
                        "top_k": 4,
                    }
                )
                hits = found.get("results") or []
                if hits:
                    lines = []
                    for index, item in enumerate(hits[:4], 1):
                        text = str(item.get("text") or "").strip()
                        if not text:
                            continue
                        lines.append(
                            f"[{index}] 《{item.get('library_name') or '知识库'}》"
                            f"（相关度 {float(item.get('score') or 0):.3f}）\n"
                            f"{text[:1200]}"
                        )
                    if lines:
                        knowledge_text = (
                            "\n\n[知识库参考]\n" + "\n\n".join(lines)
                            + "\n\n以上内容来自用户可访问的知识库。回答时优先采用；"
                            "如与用户问题无关可忽略，不要编造未出现的引用。"
                        )
            except Exception:  # noqa: BLE001 - 未配置 embedding / 无库时不阻断对话
                knowledge_text = ""
            if tools_enabled:
                toolkit = await async_build_toolkit({"session": session, "user": user})
                if super_ctx and super_ctx.get("role") == "main" and super_depth == 0:
                    from app.services.agent.collaboration.super_tools import build_super_group

                    toolkit.tool_groups.extend(build_super_group({"user_id": user.id, "super_ctx": super_ctx}))
            else:
                from agentscope.tool import Toolkit

                toolkit = Toolkit(tools=[], tool_groups=[])
            subagent_specs = (
                await async_subagent_specs({"session": session, "user": user})
                if tools_enabled else []
            )
            if subagent_specs:
                from scope.agent.delegate import register_delegate_tool

                await register_delegate_tool(
                    toolkit,
                    default_llm=llm,
                    subagents=subagent_specs,
                    owner=user.id,
                    register_task_tool=True,
                )
            skill_dirs = (
                await async_active_dirs({"session": session, "user": user})
                if tools_enabled else []
            )
            mcp_servers = (
                await async_active_servers({"session": session, "user": user})
                if tools_enabled else []
            )
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"error": str(exc)})
            return

    full_prompt = system_prompt.strip()
    if knowledge_text:
        full_prompt += knowledge_text
    if security_prompt:
        full_prompt += "\n\n" + security_prompt.strip()
    if history:
        full_prompt += "\n\n[最近对话]\n" + history

    async with AsyncSessionLocal() as session:
        context_config = {
            "trigger_ratio": float(
                await async_get_config(
                    {"session": session, "key": "agent.context.trigger_ratio", "default": 0.8}
                )
                or 0.8
            ),
            "reserve_ratio": float(
                await async_get_config(
                    {"session": session, "key": "agent.context.reserve_ratio", "default": 0.1}
                )
                or 0.1
            ),
            "context_buffer_ratio": float(
                await async_get_config(
                    {
                        "session": session,
                        "key": "agent.context.context_buffer_ratio",
                        "default": 0.2,
                    }
                )
                or 0.2
            ),
        }
    agent_cfg = {
        "name": "assistant",
        "system_prompt": full_prompt,
        "toolkit": toolkit,
        "context_config": context_config,
    }
    if skill_dirs:
        agent_cfg["skills"] = {
            "enabled": True,
            "dirs": skill_dirs,
            "ignore_missing": True,
        }
    if mcp_servers:
        agent_cfg["mcp"] = {"mcpServers": mcp_servers}
    if memory_enabled:
        memory_dir = str(
            ROOT / "backend" / "uploads" / "agents" / f"user_{user_id}" / "memory"
        )
        agent_cfg["memory"] = {
            "enabled": True,
            "type": "file",
            "path": memory_dir,
            "create_dir": True,
            "tools": {"enabled": True},
        }
    result = await async_get_agent({"llm": llm, "agent": agent_cfg})
    if result.get("code") != 200:
        yield _sse("error", {"error": result.get("message") or "Agent 初始化失败"})
        return

    runtime = AgentRuntime(result["data"]["agent"], default_approval="allow")
    user_text = content
    if attachment_text and not images and not videos:
        user_text = f"{content}\n\n{attachment_text}"
    if images or videos:
        blocks = [TextBlock(type="text", text=user_text)]
        for image in images:
            blocks.append(
                DataBlock(
                    source=Base64Source(data=image["data"], media_type=image["media_type"]),
                    name=image["name"],
                )
            )
        for video in videos:
            blocks.append(
                DataBlock(
                    source=Base64Source(data=video["data"], media_type=video["media_type"]),
                    name=video["name"],
                )
            )
        user_msg = UserMsg("user", blocks)
    else:
        user_msg = UserMsg("user", user_text)
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
        async for evt in runtime.reply_stream(user_msg):
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
            {
                "session": session,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": final_text,
                "reasoning": "".join(reasoning_parts),
                "tool_events": json.dumps(tool_events, ensure_ascii=False),
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "cache_input_tokens": usage["cache_input_tokens"],
            }
        )
        if model_usage:
            from app.models import AgentModelCall

            for model_name, item in model_usage.items():
                session.add(
                    AgentModelCall(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        message_id=assistant.id,
                        source=source,
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


async def async_run_turn(params: dict) -> dict:
    """非流式驱动一轮（超级智能体、A2A、定时任务用），返回最终文本。

    参数：user_id / conversation_id / content / super_depth / tools_enabled / source
    """
    final = ""
    payload = {
        "user_id": params["user_id"],
        "conversation_id": params["conversation_id"],
        "content": params.get("content") or "",
        "super_depth": int(params.get("super_depth") or 1),
        "tools_enabled": bool(params.get("tools_enabled", True)),
        "source": str(params.get("source") or "web"),
    }
    async for frame in async_stream_chat(payload):
        if "event: done" in frame:
            payload = frame.split("data: ", 1)[1]
            final = json.loads(payload).get("content", "")
        elif "event: error" in frame:
            payload = frame.split("data: ", 1)[1]
            raise RuntimeError(json.loads(payload).get("error", "执行失败"))
    return {"code": 200, "content": final, "submitted": False, "message": "success"}
