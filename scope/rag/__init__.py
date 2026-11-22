# -*- coding: utf-8 -*-
"""scope.rag — RAG 文档解析、切片、向量化、存储与检索。

默认后端：``sqlite``（本地 SQLite + numpy 余弦，零外部依赖）。
公共入口见 :mod:`scope.rag.rag_main`。
"""

from .rag_main import (
    async_delete_collection,
    async_delete_rag,
    async_list_documents,
    async_list_rag,
    async_rag_config,
    async_search_rag,
    async_write_rag,
)
from .knowledge import async_create_knowledge_base, async_create_rag_middleware
from .vector_store_factory import async_create_vector_store, ZvecKnowledgeBase
from .zvec_store import ZvecVectorStore
from .oceanbase_store import OceanBaseVectorStore
from .registry import query_registry, query_registry_page
from .sqlite_vector_store import SQLiteVectorStore
from .storage import async_ensure_rag_storage, async_rag_storage_status

__all__ = [
    "async_write_rag",
    "async_search_rag",
    "async_delete_rag",
    "async_delete_collection",
    "async_list_rag",
    "async_list_documents",
    "async_rag_config",
    "async_create_knowledge_base",
    "async_create_rag_middleware",
    "async_create_vector_store",
    "ZvecVectorStore",
    "ZvecKnowledgeBase",
    "OceanBaseVectorStore",
    "async_rag_storage_status",
    "async_ensure_rag_storage",
    "SQLiteVectorStore",
    "query_registry",
    "query_registry_page",
]
