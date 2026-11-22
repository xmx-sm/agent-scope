# -*- coding: utf-8 -*-
"""实时语音层：字典构建 RealtimeModel / RealtimeAgent / Transport。

直接使用官方 ``agentscope.realtime`` 与 ``agentscope.agent.RealtimeAgent``；
本层只做模型、凭证、工具包、状态、VAD、回合整理器与传输的字典接线。
"""

from .factory import (
    async_get_realtime_agent,
    async_get_realtime_model,
    async_get_realtime_transport,
)

__all__ = [
    "async_get_realtime_model",
    "async_get_realtime_transport",
    "async_get_realtime_agent",
]
