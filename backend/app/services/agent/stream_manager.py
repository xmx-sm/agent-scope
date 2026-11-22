"""SSE 生成任务托管：客户端断开后后台继续，支持同进程断线重放。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator

from app.services.agent.chat import async_stream_chat


@dataclass
class _State:
    conversation_id: str
    user_id: str
    content: str
    attachment_ids: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    done: bool = False
    task: asyncio.Task | None = None


_states: dict[str, _State] = {}
_lock = asyncio.Lock()


def _error(message: str) -> str:
    return f"event: error\ndata: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"


async def _run(state: _State) -> None:
    try:
        async for event in async_stream_chat(
            state.user_id,
            state.conversation_id,
            state.content,
            state.attachment_ids,
        ):
            state.events.append(event)
            if "event: done" in event or "event: error" in event:
                state.done = True
    except Exception as exc:  # noqa: BLE001
        state.events.append(_error(f"生成中断：{exc}"))
        state.done = True
    finally:
        state.done = True
        asyncio.create_task(_cleanup_later(state.conversation_id, state))


async def _cleanup_later(conversation_id: str, state: _State) -> None:
    await asyncio.sleep(600)
    if _states.get(conversation_id) is state and state.done:
        _states.pop(conversation_id, None)


async def start_stream(
    user_id: str,
    conversation_id: str,
    content: str,
    attachment_ids: list[str] | None = None,
) -> tuple[_State, bool]:
    async with _lock:
        current = _states.get(conversation_id)
        if current is not None and not current.done:
            return current, False
        state = _State(
            conversation_id=conversation_id,
            user_id=user_id,
            content=content,
            attachment_ids=attachment_ids or [],
        )
        _states[conversation_id] = state
        state.task = asyncio.create_task(_run(state))
        return state, True


async def _iter_state(state: _State) -> AsyncGenerator[str, None]:
    index = 0
    while True:
        while index < len(state.events):
            yield state.events[index]
            index += 1
        if state.done and index >= len(state.events):
            break
        await asyncio.sleep(0.05)


async def stream_events(
    user_id: str,
    conversation_id: str,
    content: str,
    attachment_ids: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    state, started = await start_stream(
        user_id, conversation_id, content, attachment_ids
    )
    if not started:
        yield _error("该会话正在生成中，请等待完成或使用断线续传")
        return
    async for event in _iter_state(state):
        yield event


async def resume_events(user_id: str, conversation_id: str) -> AsyncGenerator[str, None]:
    state = _states.get(conversation_id)
    if state is None or state.user_id != user_id:
        yield _error("没有可续传的生成任务")
        return
    async for event in _iter_state(state):
        yield event


async def has_stream(conversation_id: str) -> bool:
    state = _states.get(conversation_id)
    return state is not None and not state.done


__all__ = ["start_stream", "stream_events", "resume_events", "has_stream"]
