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
from .knowledge import async_create_knowledge_base, async_create_rag_middleware
from .registry import query_registry, query_registry_page
from .sqlite_vector_store import SQLiteVectorStore

__all__ = [
    "async_write_rag",
    "async_search_rag",
    "async_delete_rag",
    "async_delete_collection",
    "async_list_rag",
    "async_rag_config",
    "async_create_knowledge_base",
    "async_create_rag_middleware",
    "SQLiteVectorStore",
    "query_registry",
    "query_registry_page",
]
