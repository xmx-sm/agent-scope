"""SSE 生成任务托管：动态并发限制、有界事件缓冲与断线重放。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator

from app.services.agent.conversation.chat import async_stream_chat
from app.utils.runtime_config import async_get_runtime_config
from app.utils.runtime_limits import acquire_runtime_slot, release_runtime_slot


@dataclass
class _State:
    conversation_id: str
    user_id: str
    content: str
    attachment_ids: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    done: bool = False
    task: asyncio.Task | None = None
    buffered_bytes: int = 0
    max_buffer_bytes: int = 2 * 1024 * 1024
    retention_seconds: int = 600
    max_duration_seconds: int = 900


_states: dict[str, _State] = {}
_lock = asyncio.Lock()


def _error(message: str) -> str:
    """生成 SSE 错误事件。"""
    return f"event: error\ndata: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"


def _append_event(state: _State, event: str, terminal: bool = False) -> bool:
    """追加事件，非终止事件超限时结束本次生成。"""
    size = len(event.encode("utf-8"))
    if not terminal and state.buffered_bytes + size > state.max_buffer_bytes:
        stopped = _error("生成内容超过续传缓冲上限，请从消息列表查看已保存内容")
        state.events.append(stopped)
        state.buffered_bytes += len(stopped.encode("utf-8"))
        state.done = True
        return False
    state.events.append(event)
    state.buffered_bytes += size
    if terminal:
        state.done = True
    return True


async def _consume(state: _State) -> None:
    """消费生成器并写入有界事件缓冲。"""
    async for event in async_stream_chat(
        {
            "user_id": state.user_id,
            "conversation_id": state.conversation_id,
            "content": state.content,
            "attachment_ids": state.attachment_ids,
        }
    ):
        terminal = "event: done" in event or "event: error" in event
        if not _append_event(state, event, terminal=terminal):
            return


async def _run(state: _State) -> None:
    """在动态超时内运行生成任务并释放并发名额。"""
    try:
        await asyncio.wait_for(_consume(state), timeout=state.max_duration_seconds)
    except asyncio.TimeoutError:
        _append_event(state, _error("AI 生成超时，任务已结束"), terminal=True)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        _append_event(state, _error(f"生成中断：{exc}"), terminal=True)
    finally:
        state.done = True
        release_runtime_slot("ai_stream")
        asyncio.create_task(_cleanup_later(state.conversation_id, state))


async def _cleanup_later(conversation_id: str, state: _State) -> None:
    """按任务快照的保留时间清理已完成状态。"""
    await asyncio.sleep(state.retention_seconds)
    if _states.get(conversation_id) is state and state.done:
        _states.pop(conversation_id, None)


async def start_stream(params: dict) -> tuple[_State, bool]:
    """启动或复用会话生成任务。参数：user_id / conversation_id / content / attachment_ids。"""
    user_id = params["user_id"]
    conversation_id = params["conversation_id"]
    content = params.get("content") or ""
    attachment_ids = params.get("attachment_ids") or []
    config = await async_get_runtime_config()
    await acquire_runtime_slot(
        "ai_stream",
        "runtime.ai_max_concurrent_streams",
        8,
        "AI 对话繁忙，请稍后重试",
    )
    async with _lock:
        current = _states.get(conversation_id)
        if current is not None and not current.done:
            release_runtime_slot("ai_stream")
            return current, False
        state = _State(
            conversation_id=conversation_id,
            user_id=user_id,
            content=content,
            attachment_ids=attachment_ids or [],
            max_buffer_bytes=max(65536, int(config.get("runtime.stream_event_buffer_bytes", 2097152))),
            retention_seconds=max(30, int(config.get("runtime.stream_retention_seconds", 600))),
            max_duration_seconds=max(60, int(config.get("runtime.stream_max_duration_seconds", 900))),
        )
        _states[conversation_id] = state
        try:
            state.task = asyncio.create_task(_run(state))
        except Exception:
            _states.pop(conversation_id, None)
            release_runtime_slot("ai_stream")
            raise
        return state, True


async def _iter_state(state: _State) -> AsyncGenerator[str, None]:
    """从当前游标持续读取任务事件。"""
    index = 0
    while True:
        while index < len(state.events):
            yield state.events[index]
            index += 1
        if state.done and index >= len(state.events):
            break
        await asyncio.sleep(0.05)


async def stream_state(params: dict) -> AsyncGenerator[str, None]:
    """输出已启动任务的事件。参数：state。"""
    async for event in _iter_state(params["state"]):
        yield event


async def resume_events(params: dict) -> AsyncGenerator[str, None]:
    """重放生成任务事件。参数：user_id / conversation_id。"""
    state = _states.get(params["conversation_id"])
    if state is None or state.user_id != params["user_id"]:
        yield _error("没有可续传的生成任务")
        return
    async for event in _iter_state(state):
        yield event


async def has_stream(params: dict) -> bool:
    """判断会话是否有进行中的生成任务。参数：conversation_id。"""
    state = _states.get(params["conversation_id"])
    return state is not None and not state.done


__all__ = ["has_stream", "resume_events", "start_stream", "stream_state"]
