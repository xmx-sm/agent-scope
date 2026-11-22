# -*- coding: utf-8 -*-
"""RAG 标注注册表（SQLite）。

记录“哪个文档写进了哪个库、用的哪个 embedding 模型/维度”，用于重启后
重建、排查和前端展示。真正的向量数据在具体后端（默认 ``sqlite_db``）。

存储默认：``scope/rag/rag_sqlite/rag_db.db``，可用 ``data["rag_registry"]["path"]``
或 ``data["path"]`` 覆盖。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

_TABLE = "rag_registry"
_ALLOWED_COLUMNS = ("id", "library_type", "library_name", "doc_id",
                    "embedding_model", "provider", "dimension", "vector_type", "created_at")

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "rag_sqlite", "rag_db.db")


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def get_rag_db_path(data: dict = None) -> str:
    data = data or {}
    if isinstance(data.get("path"), str) and data["path"].strip():
        return os.path.abspath(data["path"])
    reg = data.get("rag_registry") or {}
    if isinstance(reg, dict) and reg.get("path"):
        return os.path.abspath(str(reg["path"]))
    return DEFAULT_DB_PATH


def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_type TEXT NOT NULL,
            library_name TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            provider TEXT,
            dimension INTEGER,
            vector_type TEXT,
            created_at TEXT,
            UNIQUE(library_type, library_name, doc_id)
        )
    """)
    conn.commit()
    return conn


def _library_name(data: dict, rag_cfg: dict, rag_type: str) -> str:
    cfg = rag_cfg.get(f"{rag_type}_config") or {}
    return str(cfg.get("path") or cfg.get("collection_name") or cfg.get("table_name") or "default")


def _vector_type(rag_cfg: dict, rag_type: str) -> str:
    cfg = rag_cfg.get(f"{rag_type}_config") or {}
    return str(cfg.get("vector_type") or ("sparse" if rag_type in ("zvec", "milvus") else "dense"))


def _dimension(rag_cfg: dict, rag_type: str) -> Any:
    cfg = rag_cfg.get(f"{rag_type}_config") or {}
    return cfg.get("dimension")


def record_write(data: dict) -> Dict[str, Any]:
    """写入成功后标注 doc → library / embedding。"""
    try:
        rag_cfg = data.get("rag_config") or {}
        rag_type = str(rag_cfg.get("type") or "sqlite")
        library = _library_name(data, rag_cfg, rag_type)
        file_cfg = data.get("file_config") or {}
        doc_id = str(file_cfg.get("file_name") or file_cfg.get("file_path") or "").strip()
        if not doc_id:
            return _ok([], "无文件标识，跳过标注")

        emb = data.get("embedding") or {}
        vector_type = str(rag_cfg.get("vector_type") or _vector_type(rag_cfg, rag_type))
        emb_model = emb.get("model") or ("sparse" if vector_type == "sparse" else "")
        conn = _connect(get_rag_db_path(data))
        try:
            conn.execute(
                f"""INSERT INTO {_TABLE}
                    (library_type, library_name, doc_id, embedding_model, provider,
                     dimension, vector_type, created_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(library_type, library_name, doc_id) DO UPDATE SET
                        embedding_model=excluded.embedding_model,
                        provider=excluded.provider,
                        dimension=excluded.dimension,
                        vector_type=excluded.vector_type,
                        created_at=excluded.created_at""",
                (rag_type, library, doc_id, emb_model, emb.get("provider"),
                 _dimension(rag_cfg, rag_type), vector_type,
                 datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
        finally:
            conn.close()
        return _ok([doc_id], "已标注向量模型")
    except Exception as e:
        return _err(f"标注失败：{type(e).__name__}: {e}", "record_write", code=500)


def record_delete(data: dict) -> Dict[str, Any]:
    try:
        rag_cfg = data.get("rag_config") or {}
        rag_type = str(rag_cfg.get("type") or "sqlite")
        library = _library_name(data, rag_cfg, rag_type)
        doc_id = str((data.get("delete_config") or {}).get("doc_id") or "").strip()
        conn = _connect(get_rag_db_path(data))
        try:
            conn.execute(
                f"DELETE FROM {_TABLE} WHERE library_type=? AND library_name=? AND doc_id=?",
                (rag_type, library, doc_id),
            )
            conn.commit()
        finally:
            conn.close()
        return _ok(doc_id, "标注已清除")
    except Exception as e:
        return _err(f"清除标注失败：{type(e).__name__}: {e}", "record_delete", code=500)


def record_delete_library(data: dict) -> Dict[str, Any]:
    try:
        rag_cfg = data.get("rag_config") or {}
        rag_type = str(rag_cfg.get("type") or "sqlite")
        library = _library_name(data, rag_cfg, rag_type)
        conn = _connect(get_rag_db_path(data))
        try:
            conn.execute(f"DELETE FROM {_TABLE} WHERE library_type=? AND library_name=?",
                         (rag_type, library))
            conn.commit()
        finally:
            conn.close()
        return _ok(library, "库标注已清除")
    except Exception as e:
        return _err(f"清除库标注失败：{type(e).__name__}: {e}",
                    "record_delete_library", code=500)


def query_registry(data: dict = None) -> Dict[str, Any]:
    try:
        data = data or {}
        where, params = [], []
        for key in ("library_type", "library_name", "doc_id"):
            if data.get(key):
                where.append(f"{key}=?")
                params.append(data[key])
        conn = _connect(get_rag_db_path(data))
        try:
            sql = f"SELECT * FROM {_TABLE}"
            if where:
                sql += " WHERE " + " AND ".join(where)
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()
        return _ok(rows, f"查询到 {len(rows)} 条标注")
    except Exception as e:
        return _err(f"查询失败：{type(e).__name__}: {e}", "query_registry", code=500)


def query_registry_page(data: dict = None) -> Dict[str, Any]:
    try:
        data = data or {}
        try:
            page = max(1, int(data.get("page", 1)))
            page_size = min(200, max(1, int(data.get("page_size", 10))))
        except (TypeError, ValueError):
            return _err("page / page_size 必须是整数", "query_registry_page")

        where, params = [], []
        for key in ("library_type", "library_name", "doc_id"):
            if data.get(key):
                where.append(f"{key}=?")
                params.append(data[key])
        keyword = str(data.get("keyword") or "").strip()
        if keyword:
            where.append("(library_name LIKE ? OR doc_id LIKE ? OR embedding_model LIKE ? OR provider LIKE ?)")
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw, kw])
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        conn = _connect(get_rag_db_path(data))
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM {_TABLE}{where_sql}", params).fetchone()[0]
            rows = [dict(r) for r in conn.execute(
                f"SELECT * FROM {_TABLE}{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [page_size, (page - 1) * page_size],
            ).fetchall()]
        finally:
            conn.close()
        return _ok({"items": rows, "total": total, "page": page, "page_size": page_size},
                   f"查询到 {total} 条标注")
    except Exception as e:
        return _err(f"分页查询失败：{type(e).__name__}: {e}", "query_registry_page", code=500)


__all__ = [
    "record_write",
    "record_delete",
    "record_delete_library",
    "query_registry",
    "query_registry_page",
    "get_rag_db_path",
]
