# -*- coding: utf-8 -*-
"""中间件层：把字典配置翻译成 AgentScope 官方 Middleware 实例。

官方中间件负责实际 hook 行为；本层只做：

- 字典 → 中间件实例
- ``enabled`` 开关
- 复用 `scope.llm` / `scope.rag` 构建依赖模型和知识库
- 支持自定义 MiddlewareBase 对象或类路径

不复制官方 hook、预算、Tracing、TTS 或 RAG 逻辑。
"""

from .factory import (
    async_collect_middleware_tools,
    async_get_middlewares,
    collect_middleware_tools,
)

__all__ = [
    "async_get_middlewares",
    "async_collect_middleware_tools",
    "collect_middleware_tools",
]
