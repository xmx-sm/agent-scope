# -*- coding: utf-8 -*-
"""SQLite 的 ``VectorStoreBase`` 实现，供官方 KnowledgeBase/RAGMiddleware 使用。

与 ``sqlite_db.py`` 的区别：

- ``sqlite_db.py`` 是 ``async_rag_tools`` 的直接后端（自己解析/切片/embedding）
- 本文件只实现官方向量库接口，由 ``KnowledgeBase`` 负责 embedding 与
  ``VectorRecord`` 组装

集合 = ``base_dir/{collection}.db``；每个集合一个 SQLite 文件。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from typing import Any, List

import numpy as np

from agentscope.message import DataBlock, TextBlock
from agentscope.rag import (
    Chunk,
    DocumentSummary,
    VectorRecord,
    VectorSearchResult,
    VectorStoreBase,
)

_TABLE = "chunks"
_META = "collection_meta"


def _safe_name(name: str) -> str:
    name = str(name or "").strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"非法集合名: {name!r}")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def _content_to_json(content: Any) -> dict:
    if hasattr(content, "model_dump"):
        return content.model_dump(mode="json")
    raise TypeError(f"不支持的 chunk content 类型: {type(content).__name__}")


def _content_from_json(data: dict) -> TextBlock | DataBlock:
    typ = data.get("type")
    if typ == "text":
        return TextBlock.model_validate(data)
    if typ == "data":
        return DataBlock.model_validate(data)
    raise ValueError(f"不支持的 chunk content type: {typ!r}")


def _match_filter(metadata: dict, metadata_filter: dict | None) -> bool:
    if not metadata_filter:
        return True
    return all(metadata.get(k) == v for k, v in metadata_filter.items())


def _cosine(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    qn = np.linalg.norm(query)
    if qn == 0:
        raise ValueError("查询向量长度为 0")
    mn = np.linalg.norm(matrix, axis=1)
    denom = mn * qn
    denom[denom == 0] = 1.0
    return matrix @ query / denom


class SQLiteVectorStore(VectorStoreBase):
    """本地 SQLite 向量库：一个 collection 对应一个 .db 文件。"""

    def __init__(self, base_dir: str | None = None, create: bool = False) -> None:
        if not base_dir:
            raise ValueError("SQLiteVectorStore 需要 base_dir")
        self.base_dir = os.path.abspath(str(base_dir))
        if not os.path.isdir(self.base_dir):
            if not create:
                raise FileNotFoundError(f"RAG 数据目录不存在: {self.base_dir}")
            os.makedirs(self.base_dir, exist_ok=True)

    # ── 路径 / 连接 ──────────────────────────────────────────────
    def _db_path(self, collection: str) -> str:
        return os.path.join(self.base_dir, _safe_name(collection) + ".db")

    def _connect(self, collection: str) -> sqlite3.Connection:
        path = self._db_path(collection)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_META} (
                key TEXT PRIMARY KEY,
                value TEXT
            )""")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                total_chunks INTEGER NOT NULL,
                source TEXT,
                content TEXT NOT NULL,
                metadata TEXT,
                embedding TEXT NOT NULL,
                dimension INTEGER NOT NULL
            )""")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_doc ON {_TABLE}(document_id)")
        conn.commit()
        return conn

    def _dimension(self, conn: sqlite3.Connection) -> int | None:
        row = conn.execute(f"SELECT value FROM {_META} WHERE key='dimension'").fetchone()
        return int(row["value"]) if row else None

    # ── 生命周期 ────────────────────────────────────────────────
    async def create_collection(self, name: str, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions 必须大于 0")
        conn = self._connect(name)
        try:
            current = self._dimension(conn)
            if current is not None and current != dimensions:
                raise ValueError(
                    f"集合 {name} 已存在且维度为 {current}，与请求的 {dimensions} 不一致")
            conn.execute(
                f"INSERT OR REPLACE INTO {_META} (key, value) VALUES ('dimension', ?)",
                (str(int(dimensions)),),
            )
            conn.commit()
        finally:
            conn.close()

    async def delete_collection(self, name: str) -> None:
        path = self._db_path(name)
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass

    async def has_collection(self, name: str) -> bool:
        return os.path.isfile(self._db_path(name))

    # ── 写入 / 删除 ─────────────────────────────────────────────
    async def insert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        conn = self._connect(collection)
        try:
            dim = self._dimension(conn)
            if dim is None:
                dim = len(records[0].vector)
                conn.execute(
                    f"INSERT OR REPLACE INTO {_META} (key, value) VALUES ('dimension', ?)",
                    (str(dim),),
                )
            for rec in records:
                if len(rec.vector) != dim:
                    raise ValueError(
                        f"向量维度 {len(rec.vector)} 与集合维度 {dim} 不一致")
            # 同一文档重写 = 先删旧记录（多租户时只删 metadata 公共键匹配的记录）
            doc_ids = {r.document_id for r in records}
            for doc_id in doc_ids:
                docs = [r for r in records if r.document_id == doc_id]
                common: dict[str, Any] = {}
                metas = [dict(r.chunk.metadata or {}) for r in docs]
                if metas:
                    keys = set(metas[0])
                    for m in metas[1:]:
                        keys &= set(m)
                    common = {k: metas[0][k] for k in keys}
                rows = conn.execute(
                    f"SELECT id, metadata FROM {_TABLE} WHERE document_id=?", (doc_id,)
                ).fetchall()
                for row in rows:
                    existing = json.loads(row["metadata"] or "{}")
                    if _match_filter(existing, common or None):
                        conn.execute(f"DELETE FROM {_TABLE} WHERE id=?", (row["id"],))
            for rec in records:
                chunk = rec.chunk
                conn.execute(
                    f"""INSERT OR REPLACE INTO {_TABLE}
                        (id, document_id, chunk_index, total_chunks, source,
                         content, metadata, embedding, dimension)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                    (uuid.uuid4().hex, rec.document_id,
                     int(chunk.chunk_index), int(chunk.total_chunks), chunk.source,
                     json.dumps(_content_to_json(chunk.content), ensure_ascii=False),
                     json.dumps(chunk.metadata or {}, ensure_ascii=False),
                     json.dumps([float(x) for x in rec.vector]),
                     int(dim)),
                )
            conn.commit()
        finally:
            conn.close()

    async def delete(self, collection: str, document_id: str,
                     metadata_filter: dict[str, Any] | None = None) -> None:
        if not os.path.isfile(self._db_path(collection)):
            return
        conn = self._connect(collection)
        try:
            rows = conn.execute(
                f"SELECT id, metadata FROM {_TABLE} WHERE document_id=?", (document_id,)
            ).fetchall()
            ids = [r["id"] for r in rows
                   if _match_filter(json.loads(r["metadata"] or "{}"), metadata_filter)]
            for rid in ids:
                conn.execute(f"DELETE FROM {_TABLE} WHERE id=?", (rid,))
            conn.commit()
        finally:
            conn.close()

    # ── 检索 ────────────────────────────────────────────────────
    async def search(self, collection: str, query_vector: list[float],
                     top_k: int = 5,
                     metadata_filter: dict[str, Any] | None = None) -> List[VectorSearchResult]:
        if not os.path.isfile(self._db_path(collection)):
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        if query.ndim != 1 or query.size == 0:
            raise ValueError("query_vector 必须是一维非空向量")

        conn = self._connect(collection)
        try:
            dim = self._dimension(conn)
            if dim is not None and query.size != dim:
                raise ValueError(f"查询向量维度 {query.size} 与集合维度 {dim} 不一致")
            rows = conn.execute(
                f"SELECT * FROM {_TABLE} ORDER BY document_id, chunk_index"
            ).fetchall()
        finally:
            conn.close()

        filtered = [r for r in rows
                    if _match_filter(json.loads(r["metadata"] or "{}"), metadata_filter)]
        if not filtered:
            return []
        matrix = np.vstack([np.asarray(json.loads(r["embedding"]), dtype=np.float32)
                            for r in filtered])
        scores = _cosine(query, matrix)
        order = np.argsort(-scores)[:max(1, int(top_k))]
        results: List[VectorSearchResult] = []
        for idx in order:
            r = filtered[int(idx)]
            content = _content_from_json(json.loads(r["content"]))
            chunk = Chunk(content=content, source=r["source"] or r["document_id"],
                          chunk_index=r["chunk_index"], total_chunks=r["total_chunks"],
                          metadata=json.loads(r["metadata"] or "{}"))
            results.append(VectorSearchResult(
                score=float(scores[int(idx)]),
                document_id=r["document_id"],
                chunk=chunk,
            ))
        return results

    async def list_documents(self, collection: str,
                             metadata_filter: dict[str, Any] | None = None) -> List[DocumentSummary]:
        if not os.path.isfile(self._db_path(collection)):
            return []
        conn = self._connect(collection)
        try:
            rows = conn.execute(
                f"SELECT document_id, source, metadata FROM {_TABLE} ORDER BY document_id, chunk_index"
            ).fetchall()
        finally:
            conn.close()

        docs: dict[str, dict] = {}
        for r in rows:
            meta = json.loads(r["metadata"] or "{}")
            if not _match_filter(meta, metadata_filter):
                continue
            item = docs.setdefault(r["document_id"], {
                "source": r["source"] or r["document_id"],
                "chunk_count": 0,
                "metadata": meta,
            })
            item["chunk_count"] += 1
        return [
            DocumentSummary(document_id=doc_id, source=v["source"],
                            chunk_count=v["chunk_count"], metadata=v["metadata"])
            for doc_id, v in docs.items()
        ]

    async def list_chunks(self, collection: str, document_id: str, *,
                          offset: int = 0, limit: int = 30,
                          metadata_filter: dict[str, Any] | None = None) -> List[Chunk]:
        if not os.path.isfile(self._db_path(collection)):
            return []
        conn = self._connect(collection)
        try:
            rows = conn.execute(
                f"SELECT * FROM {_TABLE} WHERE document_id=? "
                "AND chunk_index>=? AND chunk_index<? ORDER BY chunk_index",
                (document_id, int(offset), int(offset) + int(limit)),
            ).fetchall()
        finally:
            conn.close()
        out: List[Chunk] = []
        for r in rows:
            meta = json.loads(r["metadata"] or "{}")
            if not _match_filter(meta, metadata_filter):
                continue
            out.append(Chunk(
                content=_content_from_json(json.loads(r["content"])),
                source=r["source"] or r["document_id"],
                chunk_index=r["chunk_index"],
                total_chunks=r["total_chunks"],
                metadata=meta,
            ))
        return out


__all__ = ["SQLiteVectorStore"]
