# -*- coding: utf-8 -*-
"""scope.llm — 模型工厂与多模态 formatter。

公共入口在 :mod:`scope.llm.agent_model`；内部实现见 ``_factory.py``。
"""

from .agent_model import (
    async_get_asr_model,
    async_get_embedding_model,
    async_get_llm_model,
    async_get_tts_model,
    get_model_capabilities,
)
from .formatters import DashScopeVideoChatFormatter, OpenAIVideoChatFormatter

__all__ = [
    "async_get_llm_model",
    "async_get_embedding_model",
    "async_get_tts_model",
    "async_get_asr_model",
    "get_model_capabilities",
    "OpenAIVideoChatFormatter",
    "DashScopeVideoChatFormatter",
]
