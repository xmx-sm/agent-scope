# -*- coding: utf-8 -*-
"""scope.rag — RAG 文档解析、切片、向量化、存储与检索。

默认后端：``sqlite``（本地 SQLite + numpy 余弦，零外部依赖）。
公共入口见 :mod:`scope.rag.rag_main`。
"""

from .rag_main import (
    async_delete_collection,
    async_delete_rag,
    async_list_rag,
    async_rag_config,
    async_search_rag,
    async_write_rag,
)
from .registry import query_registry, query_registry_page

__all__ = [
    "async_write_rag",
    "async_search_rag",
    "async_delete_rag",
    "async_delete_collection",
    "async_list_rag",
    "async_rag_config",
    "query_registry",
    "query_registry_page",
]
