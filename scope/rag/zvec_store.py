# -*- coding: utf-8 -*-
"""Zvec 本地向量库适配。

Zvec 是阿里开源的嵌入式向量库，支持：

- ``embedding``：纯向量检索
- ``bm25``：纯全文检索
- ``hybrid``：向量 + BM25 融合

本模块同时提供：

- ``ZvecVectorStore``：官方 ``VectorStoreBase`` 适配（embedding 模式）
- ``ZvecKnowledgeBase``：支持 bm25 / embedding / hybrid 的 KnowledgeBase 兼容句柄

配置::

    {
        "type": "zvec",
        "collection": "handbook",
        "zvec_config": {
            "path": "/data/rag/u1/zvec",
            "mode": "hybrid",
            "metric_type": "cosine",
            "fts_tokenizer": "jieba",
            "fts_filters": ["lowercase"],
        },
    }
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from typing import Any, List, Optional

from agentscope.message import DataBlock, TextBlock
from agentscope.rag import (
    Chunk,
    DocumentSummary,
    KnowledgeBase,
    VectorRecord,
    VectorSearchResult,
    VectorStoreBase,
)

try:
    import zvec
except ImportError as exc:  # pragma: no cover
    zvec = None
    _ZVEC_IMPORT_ERROR = exc
else:
    _ZVEC_IMPORT_ERROR = None


def _require_zvec() -> None:
    if zvec is None:
        raise ImportError(
            "缺少 zvec 依赖，请执行 pip install zvec"
        ) from _ZVEC_IMPORT_ERROR


def _safe_name(name: str) -> str:
    text = str(name or "").strip()
    if not text or text in (".", "..") or "/" in text or "\\" in text:
        raise ValueError(f"非法集合名: {name!r}")
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)


def _content_json(content: Any) -> str:
    if hasattr(content, "model_dump"):
        return json.dumps(content.model_dump(mode="json"), ensure_ascii=False)
    return json.dumps({"type": "text", "text": str(content)}, ensure_ascii=False)


def _content_from_json(raw: str) -> Any:
    data = json.loads(raw or "{}")
    if data.get("type") == "text":
        return TextBlock.model_validate(data)
    if data.get("type") == "data":
        return DataBlock.model_validate(data)
    return TextBlock(text=str(data))


def _text_of(content: Any) -> str:
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    return ""


class ZvecVectorStore(VectorStoreBase):
    """Zvec 的 ``VectorStoreBase`` 适配。"""

    def __init__(
        self,
        base_dir: str,
        *,
        mode: str = "hybrid",
        metric_type: str = "cosine",
        fts_tokenizer: str = "jieba",
        fts_filters: Optional[List[str]] = None,
        create_dir: bool = False,
    ) -> None:
        _require_zvec()
        if not base_dir:
            raise ValueError("ZvecVectorStore 需要 base_dir")
        path = os.path.abspath(str(base_dir))
        if not os.path.isdir(path):
            if not create_dir:
                raise FileNotFoundError(f"Zvec 数据目录不存在: {path}")
            os.makedirs(path, exist_ok=True)
        self.base_dir = path
        self.mode = str(mode or "hybrid").strip().lower()
        if self.mode not in ("embedding", "bm25", "hybrid"):
            raise ValueError("zvec mode 必须是 embedding/bm25/hybrid")
        self.metric_type = str(metric_type or "cosine").strip().lower()
        self.fts_tokenizer = str(fts_tokenizer or "jieba")
        self.fts_filters = list(fts_filters or ["lowercase"])
        self._collections: dict[str, Any] = {}

    def _collection_path(self, name: str) -> str:
        return os.path.join(self.base_dir, _safe_name(name))

    def _schema(self, name: str, dimension: int):
        fields = [
            zvec.FieldSchema(
                "document_id", zvec.DataType.STRING,
                index_param=zvec.InvertIndexParam()),
            zvec.FieldSchema("chunk_index", zvec.DataType.INT64),
            zvec.FieldSchema("total_chunks", zvec.DataType.INT64),
            zvec.FieldSchema("source", zvec.DataType.STRING),
            zvec.FieldSchema("content_json", zvec.DataType.STRING),
            zvec.FieldSchema("metadata_json", zvec.DataType.STRING),
        ]
        if self.mode in ("bm25", "hybrid"):
            fields.append(zvec.FieldSchema(
                "text", zvec.DataType.STRING,
                index_param=zvec.FtsIndexParam(
                    tokenizer_name=self.fts_tokenizer,
                    filters=self.fts_filters,
                ),
            ))
        vectors = None
        if self.mode in ("embedding", "hybrid"):
            metric = {
                "cosine": zvec.MetricType.COSINE,
                "ip": zvec.MetricType.IP,
                "l2": zvec.MetricType.L2,
            }.get(self.metric_type, zvec.MetricType.COSINE)
            vectors = [zvec.VectorSchema(
                "embedding", zvec.DataType.VECTOR_FP32, max(1, int(dimension)),
                index_param=zvec.HnswIndexParam(metric_type=metric),
            )]
        return zvec.CollectionSchema(name=_safe_name(name), fields=fields, vectors=vectors)

    def _open(self, name: str, dimension: int = 1):
        key = _safe_name(name)
        if key in self._collections:
            return self._collections[key]
        path = self._collection_path(name)
        if os.path.isdir(path):
            collection = zvec.open(path)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            collection = zvec.create_and_open(path, self._schema(name, dimension))
        self._collections[key] = collection
        return collection

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        for collection in self._collections.values():
            try:
                collection.close()
            except Exception:
                pass
        self._collections.clear()

    async def create_collection(self, name: str, dimensions: int) -> None:
        self._open(name, dimensions)

    async def delete_collection(self, name: str) -> None:
        key = _safe_name(name)
        collection = self._collections.pop(key, None)
        if collection is not None:
            try:
                collection.destroy()
            except Exception:
                pass
        shutil.rmtree(self._collection_path(name), ignore_errors=True)

    async def has_collection(self, name: str) -> bool:
        return os.path.isdir(self._collection_path(name))

    async def insert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        dimension = len(records[0].vector) or 1
        col = self._open(collection, dimension)
        docs = []
        for rec in records:
            chunk = rec.chunk
            fields = {
                "document_id": rec.document_id,
                "chunk_index": int(chunk.chunk_index),
                "total_chunks": int(chunk.total_chunks),
                "source": chunk.source or rec.document_id,
                "content_json": _content_json(chunk.content),
                "metadata_json": json.dumps(chunk.metadata or {}, ensure_ascii=False),
            }
            if self.mode in ("bm25", "hybrid"):
                fields["text"] = _text_of(chunk.content)
            vectors = None
            if self.mode in ("embedding", "hybrid"):
                vectors = {"embedding": [float(x) for x in rec.vector]}
            docs.append(zvec.Doc(
                id=f"{rec.document_id}::{chunk.chunk_index}",
                vectors=vectors,
                fields=fields,
            ))
        col.upsert(docs)

    async def delete(
        self,
        collection: str,
        document_id: str,
        metadata_filter: dict[str, Any] | None = None,
    ) -> None:
        if not os.path.isdir(self._collection_path(collection)):
            return
        col = self._open(collection)
        ids = [
            doc.id for doc in col.iter_docs(output_fields=["document_id"])
            if doc.fields.get("document_id") == document_id
            and self._match(doc.fields, metadata_filter)
        ]
        if ids:
            col.delete(ids=ids)

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> List[VectorSearchResult]:
        if self.mode == "bm25":
            raise ValueError("zvec mode=bm25 没有向量检索，请通过 ZvecKnowledgeBase.search 传文本")
        if not os.path.isdir(self._collection_path(collection)):
            return []
        col = self._open(collection)
        results = col.query(
            queries=zvec.Query(field_name="embedding", vector=query_vector),
            topk=max(1, int(top_k) * 4),
            output_fields=[
                "document_id", "chunk_index", "total_chunks",
                "source", "content_json", "metadata_json", "text",
            ],
        )
        return self._convert(results, top_k, metadata_filter, fts=False)

    async def search_text(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> List[VectorSearchResult]:
        if self.mode == "embedding":
            raise ValueError("zvec mode=embedding 不支持纯 BM25 检索")
        if not os.path.isdir(self._collection_path(collection)):
            return []
        col = self._open(collection)
        results = col.query(
            queries=zvec.Query(
                field_name="text",
                fts=zvec.Fts(match_string=str(query)),
            ),
            topk=max(1, int(top_k) * 4),
            output_fields=[
                "document_id", "chunk_index", "total_chunks",
                "source", "content_json", "metadata_json",
            ],
        )
        return self._convert(results, top_k, metadata_filter, fts=True)

    async def search_hybrid(
        self,
        collection: str,
        query: str,
        query_vector: list[float],
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> List[VectorSearchResult]:
        if self.mode != "hybrid":
            raise ValueError("zvec search_hybrid 需要 mode=hybrid")
        if not os.path.isdir(self._collection_path(collection)):
            return []
        col = self._open(collection, len(query_vector) or 1)
        results = col.query(
            queries=[
                zvec.Query(field_name="embedding", vector=query_vector),
                zvec.Query(
                    field_name="text",
                    fts=zvec.Fts(match_string=str(query)),
                ),
            ],
            topk=max(1, int(top_k) * 4),
            reranker=zvec.RrfReRanker(),
            output_fields=[
                "document_id", "chunk_index", "total_chunks",
                "source", "content_json", "metadata_json", "text",
            ],
        )
        return self._convert(results, top_k, metadata_filter, fts=True)

    @staticmethod
    def _match(fields: dict, metadata_filter: dict | None) -> bool:
        if not metadata_filter:
            return True
        meta = {}
        try:
            meta = json.loads(fields.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            pass
        return all(meta.get(k) == v for k, v in metadata_filter.items())

    def _convert(self, results, top_k: int, metadata_filter: dict | None,
                 *, fts: bool = False):
        out = []
        for doc in results:
            fields = dict(doc.fields or {})
            if not self._match(fields, metadata_filter):
                continue
            meta = json.loads(fields.get("metadata_json") or "{}")
            chunk = Chunk(
                content=_content_from_json(fields.get("content_json") or ""),
                source=fields.get("source") or fields.get("document_id") or "",
                chunk_index=int(fields.get("chunk_index") or 0),
                total_chunks=int(fields.get("total_chunks") or 0),
                metadata=meta,
            )
            score = float(doc.score or 0.0)
            if not fts:
                if self.metric_type == "l2":
                    score = -score
                elif self.metric_type == "cosine":
                    score = 1.0 - score
            out.append(VectorSearchResult(
                score=score,
                document_id=fields.get("document_id") or "",
                chunk=chunk,
            ))
            if len(out) >= top_k:
                break
        return out

    async def list_documents(
        self,
        collection: str,
        metadata_filter: dict[str, Any] | None = None,
    ) -> List[DocumentSummary]:
        if not os.path.isdir(self._collection_path(collection)):
            return []
        col = self._open(collection)
        docs: dict[str, DocumentSummary] = {}
        for doc in col.iter_docs(output_fields=[
            "document_id", "source", "content_json", "metadata_json",
        ]):
            fields = dict(doc.fields or {})
            if not self._match(fields, metadata_filter):
                continue
            doc_id = fields.get("document_id") or ""
            if not doc_id:
                continue
            meta = json.loads(fields.get("metadata_json") or "{}")
            if doc_id in docs:
                docs[doc_id].chunk_count += 1
            else:
                docs[doc_id] = DocumentSummary(
                    document_id=doc_id,
                    source=fields.get("source") or doc_id,
                    chunk_count=1,
                    metadata=meta,
                )
        return list(docs.values())


class ZvecKnowledgeBase(KnowledgeBase):
    """支持 zvec bm25 / embedding / hybrid 的 KnowledgeBase。"""

    def __init__(self, *args, zvec_mode: str = "hybrid", **kwargs):
        super().__init__(*args, **kwargs)
        self.zvec_mode = str(zvec_mode or "hybrid")

    async def ensure_collection(self) -> None:
        if self._collection_ready:
            return
        dimensions = getattr(self.embedding_model, "dimensions", 1) or 1
        if self.zvec_mode == "bm25":
            dimensions = 1
        if not await self.vector_store.has_collection(self.collection):
            await self.vector_store.create_collection(
                self.collection, dimensions=int(dimensions))
        self._collection_ready = True

    async def insert_document(self, chunks, document_id=None,
                              document_metadata=None):
        if self.zvec_mode != "bm25":
            return await super().insert_document(
                chunks, document_id=document_id,
                document_metadata=document_metadata)
        if not chunks:
            return document_id or uuid.uuid4().hex
        document_id = document_id or uuid.uuid4().hex
        await self.ensure_collection()
        from agentscope.rag import VectorRecord

        prepared = [
            chunk.model_copy(update={"metadata": {
                **(document_metadata or {}),
                **chunk.metadata,
                **(self.metadata_filter or {}),
            }})
            for chunk in chunks
        ]
        await self.vector_store.insert(
            self.collection,
            [VectorRecord(vector=[], document_id=document_id, chunk=chunk)
             for chunk in prepared],
        )
        return document_id

    async def search(self, queries, top_k=5, score_threshold=None):
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        if not queries:
            return []
        await self.ensure_collection()
        store: ZvecVectorStore = self.vector_store
        texts = []
        for query in queries:
            if isinstance(query, TextBlock):
                texts.append(query.text)
            elif isinstance(query, str):
                texts.append(query)
        if not texts:
            return []
        if self.zvec_mode == "bm25":
            groups = [
                await store.search_text(
                    self.collection, text, top_k, self.metadata_filter)
                for text in texts
            ]
        elif self.zvec_mode == "embedding":
            return await super().search(
                queries, top_k=top_k, score_threshold=score_threshold)
        else:
            response = await self.embedding_model(texts)
            groups = [
                await store.search_hybrid(
                    self.collection, text, vector, top_k, self.metadata_filter)
                for text, vector in zip(texts, response.embeddings)
            ]
        best = {}
        for group in groups:
            for result in group:
                if score_threshold is not None and result.score < score_threshold:
                    continue
                key = (result.document_id, result.chunk.chunk_index)
                if key not in best or result.score > best[key].score:
                    best[key] = result
        return sorted(best.values(), key=lambda x: x.score, reverse=True)[:top_k]


__all__ = ["ZvecVectorStore", "ZvecKnowledgeBase"]
