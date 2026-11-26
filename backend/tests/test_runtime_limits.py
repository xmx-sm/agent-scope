"""运行资源动态限制测试。"""

import asyncio

import pytest

from app.core.deps import ApiError
from app.services.agent.runtime import stream_manager
from app.utils import runtime_limits


def test_event_buffer_limit_terminates_stream():
    state = stream_manager._State(
        conversation_id="conversation",
        user_id="user",
        content="hello",
        max_buffer_bytes=8,
    )
    assert stream_manager._append_event(state, "event: text_delta\n\n") is False
    assert state.done is True
    assert "超过续传缓冲上限" in state.events[-1]


def test_dynamic_stream_limit_rejects_second_task(monkeypatch):
    async def runtime_config():
        """返回单任务并发配置。"""
        return {
            "runtime.ai_max_concurrent_streams": 1,
            "runtime.stream_event_buffer_bytes": 2097152,
            "runtime.stream_retention_seconds": 600,
            "runtime.stream_max_duration_seconds": 900,
        }

    async def pending_stream(params):
        """保持第一个生成任务运行。"""
        await asyncio.Event().wait()
        if False:
            yield ""

    monkeypatch.setattr(stream_manager, "async_get_runtime_config", runtime_config)
    monkeypatch.setattr(runtime_limits, "async_get_runtime_config", runtime_config)
    monkeypatch.setattr(stream_manager, "async_stream_chat", pending_stream)

    async def scenario():
        """验证并发准入与取消后的名额释放。"""
        first, started = await stream_manager.start_stream(
            {"user_id": "user", "conversation_id": "first", "content": "hello"}
        )
        assert started is True
        try:
            with pytest.raises(ApiError) as error:
                await stream_manager.start_stream(
                    {"user_id": "user", "conversation_id": "second", "content": "hello"}
                )
            assert error.value.code == 429
        finally:
            first.task.cancel()
            await asyncio.gather(first.task, return_exceptions=True)
            stream_manager._states.clear()

    asyncio.run(scenario())
