# -*- coding: utf-8 -*-
"""通用 KnowledgeBase 后端（直接工具模式）。

用于 ``tools/rag`` 的 qdrant / milvus / mongodb / elasticsearch /
zvec / oceanbase 后端。复用官方 ``KnowledgeBase`` 与
``async_create_knowledge_base``，不再为每个后端重写文件解析、切片和
embedding 逻辑。

SQLite 仍走 ``sqlite_db.py`` 的专用直连实现。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from .common import async_get_chunks
from .knowledge import async_create_knowledge_base
from .vector_store_factory import _backend, _section


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _item(data: dict) -> tuple[dict, str, dict]:
    rag_cfg = data.get("rag_config") or {}
    backend = _backend({}, data)
    if backend == "mongodb":
        backend = "mongo"
    if backend == "es":
        backend = "elasticsearch"
    if backend == "ob":
        backend = "oceanbase"
    block_name = {
        "mongo": "mongo_config",
        "mongodb": "mongo_config",
        "elasticsearch": "elasticsearch_config",
        "es": "elasticsearch_config",
        "oceanbase": "oceanbase_config",
        "ob": "oceanbase_config",
        "zvec": "zvec_config",
        "qdrant": "qdrant_config",
        "milvus": "milvus_config",
    }.get(backend, f"{backend}_config")
    cfg = _section(rag_cfg, data, block_name)
    collection = str(
        cfg.get("collection")
        or rag_cfg.get("collection")
        or cfg.get("path")
        or "default"
    )
    if backend == "zvec":
        # path 是数据根目录，collection 仍是逻辑名
        collection = str(cfg.get("collection") or rag_cfg.get("collection") or "default")
    item = {
        "name": collection,
        "description": str(rag_cfg.get("description") or collection),
        "collection": collection,
        "type": backend,
        block_name: cfg,
        "embedding_model": data.get("embedding_model"),
        "metadata_filter": cfg.get("metadata_filter") or rag_cfg.get("metadata_filter"),
    }
    if data.get("embedding") is not None:
        item["embedding"] = data["embedding"]
    return item, backend, cfg


async def _knowledge(data: dict):
    item, backend, cfg = _item(data)
    r = await async_create_knowledge_base({**data, "knowledge_base": item})
    if r.get("code") != 200:
        return r, None, None, None
    return r, r["data"]["knowledge_base"], r["data"]["vector_store"], backend


async def _close(store: Any) -> None:
    try:
        await store.__aexit__(None, None, None)
    except Exception:
        pass


async def async_write_rag_kb(data: dict) -> Dict[str, Any]:
    fn = "async_write_rag_kb"
    try:
        chunks_r = await async_get_chunks(data)
        if chunks_r.get("code") != 200:
            return chunks_r
        r, kb, store, backend = await _knowledge(data)
        if r.get("code") != 200:
            return r
        try:
            file_cfg = data.get("file_config") or {}
            doc_id = str(
                file_cfg.get("file_name") or file_cfg.get("file_path") or "").strip()
            if not doc_id:
                return _err("缺少 file_config.file_name / file_path（作为 doc_id）", fn)
            ids = await kb.insert_document(
                chunks_r["data"], document_id=doc_id,
                document_metadata={"filename": doc_id},
            )
            return _ok(ids, f"写入文档 {doc_id}")
        finally:
            await _close(store)
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"写入失败：{type(e).__name__}: {e}", fn, 500)


async def async_search_rag_kb(data: dict) -> Dict[str, Any]:
    fn = "async_search_rag_kb"
    try:
        search = data.get("search_config") or {}
        query = search.get("query")
        if not isinstance(query, str) or not query.strip():
            return _err("缺少 search_config.query", fn)
        r, kb, store, backend = await _knowledge(data)
        if r.get("code") != 200:
            return r
        try:
            top_k = max(1, min(int(search.get("top_k", 10)), 200))
            threshold = search.get("score_threshold")
            results = await kb.search(
                [query], top_k=top_k,
                score_threshold=float(threshold) if threshold is not None else None,
            )
            hits = [{
                "id": f"{x.document_id}::{x.chunk.chunk_index}",
                "text": getattr(x.chunk.content, "text", "") or "",
                "metadata": x.chunk.metadata or {},
                "score": x.score,
                "document_id": x.document_id,
            } for x in results]
            return _ok(hits, f"命中 {len(hits)} 条")
        finally:
            await _close(store)
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"检索失败：{type(e).__name__}: {e}", fn, 500)


async def async_delete_rag_kb(data: dict) -> Dict[str, Any]:
    fn = "async_delete_rag_kb"
    try:
        doc_id = str((data.get("delete_config") or {}).get("doc_id") or "").strip()
        if not doc_id:
            return _err("缺少 delete_config.doc_id", fn)
        r, kb, store, backend = await _knowledge(data)
        if r.get("code") != 200:
            return r
        try:
            await kb.delete_document(doc_id)
            return _ok(doc_id, f"已删除文档 {doc_id}")
        finally:
            await _close(store)
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"删除失败：{type(e).__name__}: {e}", fn, 500)


async def async_delete_collection_rag_kb(data: dict) -> Dict[str, Any]:
    fn = "async_delete_collection_rag_kb"
    try:
        r, kb, store, backend = await _knowledge(data)
        if r.get("code") != 200:
            return r
        try:
            await store.delete_collection(kb.collection)
            return _ok(kb.collection, f"集合 {kb.collection} 已删除")
        finally:
            await _close(store)
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"删除集合失败：{type(e).__name__}: {e}", fn, 500)


async def async_list_rag_kb(data: dict) -> Dict[str, Any]:
    fn = "async_list_rag_kb"
    try:
        r, kb, store, backend = await _knowledge(data)
        if r.get("code") != 200:
            return r
        try:
            exists = await store.has_collection(kb.collection)
            return _ok([kb.collection] if exists else [], f"后端 {backend}")
        finally:
            await _close(store)
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"列出集合失败：{type(e).__name__}: {e}", fn, 500)


async def async_list_documents_rag_kb(data: dict) -> Dict[str, Any]:
    fn = "async_list_documents_rag_kb"
    try:
        r, kb, store, backend = await _knowledge(data)
        if r.get("code") != 200:
            return r
        try:
            docs = await kb.list_documents()
            return _ok([{
                "document_id": d.document_id,
                "source": d.source,
                "chunk_count": d.chunk_count,
                "metadata": d.metadata,
            } for d in docs], f"共 {len(docs)} 个文档")
        finally:
            await _close(store)
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"列出文档失败：{type(e).__name__}: {e}", fn, 500)


__all__ = [
    "async_write_rag_kb",
    "async_search_rag_kb",
    "async_delete_rag_kb",
    "async_delete_collection_rag_kb",
    "async_list_rag_kb",
    "async_list_documents_rag_kb",
]
