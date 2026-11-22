# -*- coding: utf-8 -*-
"""OceanBase 向量库适配（基于 pyobvector）。

配置::

    {
        "type": "oceanbase",
        "oceanbase_config": {
            "uri": "127.0.0.1:2881",
            "user": "root@test",
            "password": "...",
            "db_name": "test",
            "metric_type": "l2",
        },
    }

``uri`` 支持 OceanBase / SeekDB 的 SQL 连接地址；也接受 ``api_url`` / ``host``
作为别名。需要 ``pip install pyobvector``。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, List

from agentscope.rag import (
    Chunk,
    DocumentSummary,
    VectorRecord,
    VectorSearchResult,
    VectorStoreBase,
)


def _hash_id(document_id: str, chunk_index: int) -> str:
    return hashlib.sha256(
        f"{document_id}\0{chunk_index}".encode("utf-8")).hexdigest()


class OceanBaseVectorStore(VectorStoreBase):
    """pyobvector / OceanBase 的 VectorStoreBase 适配。"""

    def __init__(
        self,
        uri: str,
        *,
        user: str = "root@test",
        password: str = "",
        db_name: str = "test",
        metric_type: str = "l2",
        index_type: str = "HNSW",
        client_kwargs: dict | None = None,
    ) -> None:
        if not uri:
            raise ValueError("OceanBaseVectorStore 需要 uri")
        self.uri = uri
        self.user = user
        self.password = password
        self.db_name = db_name
        self.metric_type = str(metric_type or "l2").lower()
        self.index_type = str(index_type or "HNSW").upper()
        self.client_kwargs = client_kwargs or {}
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from pyobvector import MilvusLikeClient
            except ImportError as e:
                raise ImportError(
                    "缺少 pyobvector 依赖，请执行 pip install pyobvector") from e
            self._client = MilvusLikeClient(
                uri=self.uri,
                user=self.user,
                password=self.password,
                db_name=self.db_name,
                **self.client_kwargs,
            )
        return self._client

    async def create_collection(self, name: str, dimensions: int) -> None:
        client = self._get_client()
        if client.has_collection(name):
            return
        from pyobvector import DataType, VecIndexType

        schema = client.create_schema()
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=int(dimensions))
        schema.add_field("document_id", DataType.VARCHAR, max_length=512)
        schema.add_field("chunk", DataType.JSON)
        schema.add_field("metadata", DataType.JSON)
        index_type = getattr(VecIndexType, self.index_type, VecIndexType.HNSW)
        params = client.prepare_index_params()
        params.add_index(
            field_name="vector",
            index_type=index_type,
            index_name="vector_idx",
            metric_type=self.metric_type,
        )
        await asyncio.to_thread(
            client.create_collection,
            collection_name=name,
            schema=schema,
            index_params=params,
        )

    async def delete_collection(self, name: str) -> None:
        await asyncio.to_thread(self._get_client().drop_collection, name)

    async def has_collection(self, name: str) -> bool:
        return await asyncio.to_thread(self._get_client().has_collection, name)

    async def insert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        await asyncio.to_thread(
            self._get_client().upsert,
            collection_name=collection,
            data=[
                {
                    "id": _hash_id(r.document_id, r.chunk.chunk_index),
                    "vector": [float(x) for x in r.vector],
                    "document_id": r.document_id,
                    "chunk": r.chunk.model_dump(mode="json"),
                    "metadata": r.chunk.metadata or {},
                }
                for r in records
            ],
        )

    async def delete(self, collection: str, document_id: str,
                     metadata_filter: dict | None = None) -> None:
        ids = await self._find_ids(collection, document_id, metadata_filter)
        if ids:
            await asyncio.to_thread(
                self._get_client().delete,
                collection_name=collection,
                ids=ids,
            )

    async def _find_ids(self, collection: str, document_id: str,
                        metadata_filter: dict | None) -> list[str]:
        try:
            rows = await asyncio.to_thread(
                self._get_client().query,
                collection_name=collection,
                output_fields=["id", "document_id", "metadata"],
            )
        except Exception:
            return []
        result = []
        for row in rows or []:
            if row.get("document_id") != document_id:
                continue
            meta = row.get("metadata") or {}
            if metadata_filter and any(meta.get(k) != v for k, v in metadata_filter.items()):
                continue
            if row.get("id") is not None:
                result.append(str(row["id"]))
        return result

    async def search(self, collection: str, query_vector: list[float],
                     top_k: int = 5,
                     metadata_filter: dict | None = None) -> List[VectorSearchResult]:
        try:
            rows = await asyncio.to_thread(
                self._get_client().search,
                collection_name=collection,
                data=[float(x) for x in query_vector],
                anns_field="vector",
                limit=max(1, int(top_k) * 4),
                output_fields=["id", "document_id", "chunk", "metadata"],
                search_params={"metric_type": self.metric_type},
                with_dist=True,
            )
        except Exception:
            return []
        out = []
        for i, row in enumerate(rows or []):
            meta = row.get("metadata") or {}
            if metadata_filter and any(meta.get(k) != v for k, v in metadata_filter.items()):
                continue
            chunk_data = row.get("chunk") or {}
            if isinstance(chunk_data, str):
                chunk_data = json.loads(chunk_data)
            chunk = Chunk.model_validate(chunk_data)
            score = 1.0 / (i + 1)
            values = list(row.values())
            if values and isinstance(values[-1], (int, float)):
                dist = float(values[-1])
                score = -dist if self.metric_type == "l2" else 1.0 - dist
            out.append(VectorSearchResult(
                score=score,
                document_id=row.get("document_id") or "",
                chunk=chunk,
            ))
            if len(out) >= top_k:
                break
        return out

    async def list_documents(self, collection: str,
                             metadata_filter: dict | None = None) -> List[DocumentSummary]:
        try:
            rows = await asyncio.to_thread(
                self._get_client().query,
                collection_name=collection,
                output_fields=["document_id", "chunk", "metadata", "id"],
            )
        except Exception:
            return []
        docs: dict[str, DocumentSummary] = {}
        for row in rows or []:
            meta = row.get("metadata") or {}
            if metadata_filter and any(meta.get(k) != v for k, v in metadata_filter.items()):
                continue
            doc_id = row.get("document_id") or ""
            if not doc_id:
                continue
            chunk_data = row.get("chunk") or {}
            if isinstance(chunk_data, str):
                chunk_data = json.loads(chunk_data)
            chunk = Chunk.model_validate(chunk_data)
            if doc_id in docs:
                docs[doc_id].chunk_count += 1
            else:
                docs[doc_id] = DocumentSummary(
                    document_id=doc_id,
                    source=chunk.source or doc_id,
                    chunk_count=1,
                    metadata=meta,
                )
        return list(docs.values())


__all__ = ["OceanBaseVectorStore"]
