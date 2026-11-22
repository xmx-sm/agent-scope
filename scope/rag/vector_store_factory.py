# -*- coding: utf-8 -*-
"""向量库后端工厂。

每个后端有独立配置段：

- ``sqlite_config``
- ``qdrant_config``
- ``milvus_config``
- ``mongo_config``
- ``elasticsearch_config``
- ``zvec_config``
- ``oceanbase_config``

连接/选择类参数没有源码兜底：缺少时返回 400。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from agentscope.rag import (
    ElasticsearchStore,
    MilvusLiteStore,
    MongoDBStore,
    QdrantStore,
)

try:
    from .sqlite_vector_store import SQLiteVectorStore
    from .zvec_store import ZvecVectorStore, ZvecKnowledgeBase
    from .oceanbase_store import OceanBaseVectorStore
except ImportError:
    from sqlite_vector_store import SQLiteVectorStore
    from zvec_store import ZvecVectorStore, ZvecKnowledgeBase
    from oceanbase_store import OceanBaseVectorStore


def _err(message: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": "scope.rag.vector_store",
            "message": f"错误：{message}"}


def _ok(data: Any, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _section(item: dict, data: dict, name: str) -> dict:
    for source in (item, data):
        value = source.get(name)
        if value is not None:
            if not isinstance(value, dict):
                raise ValueError(f"{name} 必须是字典")
            return dict(value)
    return {}


def _backend(item: dict, data: dict) -> str:
    raw = item.get("type") or item.get("rag_type")
    if raw is None:
        vs = item.get("vector_store")
        if isinstance(vs, dict):
            raw = vs.get("type")
    if raw is None:
        vs = data.get("vector_store")
        if isinstance(vs, dict):
            raw = vs.get("type")
    if raw is None:
        raw = (data.get("rag_config") or {}).get("type")
    if raw is None:
        raw = data.get("type")
    return str(raw or "sqlite").strip().lower()


def _abs_path(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"缺少参数 {name}")
    if not os.path.isabs(os.path.expanduser(text)):
        raise ValueError(f"{name} 必须是绝对路径: {text}")
    return os.path.abspath(os.path.expanduser(text))


def _create_dir(value: Any, create: Any) -> str:
    path = _abs_path(value, "zvec_config.path")
    if not os.path.isdir(path):
        if not bool(create):
            raise ValueError(f"Zvec 数据目录不存在: {path}（可传 create_dir=True）")
        os.makedirs(path, exist_ok=True)
    return path


async def async_create_vector_store(
    data: dict,
    item: dict = None,
) -> Dict[str, Any]:
    """构建一个向量库实例，并返回 (store, backend, config)。"""
    item = item or {}
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典")
    backend = _backend(item, data)

    if backend == "sqlite":
        sqlite_cfg = _section(item, data, "sqlite_config")
        base_dir = (
            sqlite_cfg.get("base_dir")
            or (data.get("rag_config") or {}).get("sqlite_config", {}).get("base_dir")
        )
        if not base_dir:
            raise ValueError("缺少参数 sqlite_config.base_dir")
        base = _abs_path(base_dir, "sqlite_config.base_dir")
        create = sqlite_cfg.get("create_dir")
        if create is None:
            create = data.get("create_dir", False)
        if not os.path.isdir(base) and not bool(create):
            raise ValueError(f"RAG 数据目录不存在: {base}（可传 create_dir=True）")
        store = SQLiteVectorStore(base, create=bool(create))
        return _ok({"store": store, "backend": backend, "config": sqlite_cfg},
                   "SQLite 向量库创建成功")

    if backend == "zvec":
        cfg = _section(item, data, "zvec_config")
        base = _create_dir(cfg.get("path"), cfg.get("create_dir", data.get("create_dir", False)))
        store = ZvecVectorStore(
            base,
            mode=cfg.get("mode", "hybrid"),
            metric_type=cfg.get("metric_type", "cosine"),
            fts_tokenizer=cfg.get("fts_tokenizer", "jieba"),
            fts_filters=cfg.get("fts_filters"),
            create_dir=True,
        )
        return _ok({"store": store, "backend": backend, "config": cfg,
                    "knowledge_base": ZvecKnowledgeBase},
                   "Zvec 向量库创建成功")

    if backend == "qdrant":
        cfg = _section(item, data, "qdrant_config")
        location = cfg.get("location")
        url = cfg.get("url")
        path = cfg.get("path")
        if not any((location, url, path)):
            raise ValueError("缺少参数 qdrant_config.location / url / path")
        if path:
            path = _abs_path(path, "qdrant_config.path")
        store = QdrantStore(
            location=location,
            url=url,
            path=path,
            api_key=cfg.get("api_key"),
            distance=cfg.get("distance", "Cosine"),
            client_kwargs=cfg.get("client_kwargs"),
        )
        return _ok({"store": store, "backend": backend, "config": cfg},
                   "Qdrant 向量库创建成功")

    if backend == "milvus":
        cfg = _section(item, data, "milvus_config")
        uri = cfg.get("uri") or cfg.get("path")
        if not uri:
            raise ValueError("缺少参数 milvus_config.uri")
        if cfg.get("path") or (isinstance(uri, str) and uri.endswith(".db")):
            uri = _abs_path(uri, "milvus_config.uri")
        store = MilvusLiteStore(
            uri=uri,
            metric_type=cfg.get("metric_type", "COSINE"),
            index_type=cfg.get("index_type", "AUTOINDEX"),
            client_kwargs=cfg.get("client_kwargs"),
            batch_size=int(cfg.get("batch_size", 256)),
        )
        return _ok({"store": store, "backend": backend, "config": cfg},
                   "Milvus 向量库创建成功")

    if backend in ("mongo", "mongodb"):
        cfg = _section(item, data, "mongo_config")
        uri = cfg.get("uri")
        database = cfg.get("database")
        if not uri or not database:
            raise ValueError("缺少参数 mongo_config.uri / database")
        store = MongoDBStore(
            uri=uri,
            database=database,
            distance=cfg.get("distance", "cosine"),
            index_name=cfg.get("index_name", "vector_index"),
            filter_fields=cfg.get("filter_fields"),
            client_kwargs=cfg.get("client_kwargs"),
        )
        return _ok({"store": store, "backend": "mongodb", "config": cfg},
                   "MongoDB 向量库创建成功")

    if backend in ("elasticsearch", "es"):
        cfg = _section(item, data, "elasticsearch_config")
        hosts = cfg.get("hosts")
        if not hosts:
            raise ValueError("缺少参数 elasticsearch_config.hosts")
        store = ElasticsearchStore(
            hosts=hosts,
            num_candidates=int(cfg.get("num_candidates", 100)),
            refresh=cfg.get("refresh", "wait_for"),
            client_kwargs=cfg.get("client_kwargs"),
        )
        return _ok({"store": store, "backend": "elasticsearch", "config": cfg},
                   "Elasticsearch 向量库创建成功")

    if backend in ("oceanbase", "ob"):
        cfg = _section(item, data, "oceanbase_config")
        uri = cfg.get("uri") or cfg.get("api_url") or cfg.get("host")
        if not uri:
            raise ValueError("缺少参数 oceanbase_config.uri（或 api_url / host）")
        store = OceanBaseVectorStore(
            uri=uri,
            user=cfg.get("user", "root@test"),
            password=cfg.get("password", ""),
            db_name=cfg.get("db_name", cfg.get("database", "test")),
            metric_type=cfg.get("metric_type", "l2"),
            index_type=cfg.get("index_type", "HNSW"),
            client_kwargs=cfg.get("client_kwargs"),
        )
        return _ok({"store": store, "backend": "oceanbase", "config": cfg},
                   "OceanBase 向量库创建成功")

    raise ValueError(
        "不支持的向量库类型: "
        f"{backend}（sqlite/qdrant/milvus/mongodb/elasticsearch/zvec/oceanbase）")


__all__ = ["async_create_vector_store", "ZvecKnowledgeBase"]
