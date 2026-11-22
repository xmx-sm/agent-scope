# -*- coding: utf-8 -*-
"""SQLite 本地向量库后端（零外部依赖，numpy 余弦检索）。

定位：单机/开发/轻量知识库的默认后端。写入时把 chunk 文本、metadata 和
embedding JSON 存进一个 SQLite 文件；检索时在内存里做余弦相似度。

配置（``data["rag_config"]["sqlite_config"]``）::

    path(str, 可选)        集合名，默认 "default"；也接受绝对 .db 文件路径
    base_dir(str, 可选)    数据根目录，默认 {cwd}/rag_db
    metric_type(str, 可选) 仅支持 cosine（默认）

不支持 sparse / hybrid；需要 BM25/稀疏检索请接其他后端。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np

from .common import async_get_embeddings, async_get_query_vector, get_chunk_metadata, get_chunk_text

_TABLE = "rag_chunks"


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _safe_name(name: str) -> str:
    name = str(name or "").strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"非法集合名: {name!r}")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def _target(data: dict) -> Tuple[str, str]:
    """返回 (db_file, collection_name)。"""
    rag_cfg = data.get("rag_config") or {}
    cfg = rag_cfg.get("sqlite_config") or {}
    raw = str(cfg.get("path") or cfg.get("collection_name") or "default").strip()

    if os.path.isabs(raw) and raw.endswith(".db"):
        db_file = raw
        name = os.path.splitext(os.path.basename(db_file))[0]
    else:
        name = _safe_name(raw)
        base_dir = os.path.abspath(str(cfg.get("base_dir") or os.path.join(os.getcwd(), "rag_db")))
        db_file = os.path.join(base_dir, name + ".db")
    return os.path.abspath(db_file), name


def _connect(db_file: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {_TABLE} (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                metadata TEXT,
                embedding TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                created_at TEXT
            )"""
    )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_doc ON {_TABLE}(doc_id)")
    conn.commit()
    return conn


def _as_vector(value: Any) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float32)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("embedding 必须是一维非空向量")
    return arr


def _cosine(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    qn = np.linalg.norm(query)
    if qn == 0:
        raise ValueError("查询向量长度为 0")
    mn = np.linalg.norm(matrix, axis=1)
    denom = mn * qn
    denom[denom == 0] = 1.0
    return matrix @ query / denom


async def _write(data: dict) -> Dict[str, Any]:
    fn = "async_write_rag_sqlite"
    emb = await async_get_embeddings(data)
    if emb.get("code") != 200:
        return emb
    chunks = emb["data"]["chunks"]
    texts = emb["data"]["texts"]
    embeddings = emb["data"]["embeddings"]

    db_file, name = _target(data)
    conn = _connect(db_file)
    try:
        file_cfg = data.get("file_config") or {}
        doc_id = str(file_cfg.get("file_name") or file_cfg.get("file_path") or "").strip()
        if not doc_id:
            return _err("缺少 file_config.file_name / file_path（作为 doc_id）", fn)

        # 同一文档重写 = 先删旧 chunk，保证幂等
        conn.execute(f"DELETE FROM {_TABLE} WHERE doc_id=?", (doc_id,))
        ids: List[str] = []
        now = datetime.now().isoformat(timespec="seconds")
        for i, (chunk, text, vector) in enumerate(zip(chunks, texts, embeddings)):
            meta = get_chunk_metadata(chunk)
            meta["text"] = text
            vec = _as_vector(vector)
            chunk_id = f"{doc_id}::{i}"
            conn.execute(
                f"INSERT INTO {_TABLE} (id, doc_id, chunk_index, text, metadata, embedding, dimension, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (chunk_id, doc_id, i, text, json.dumps(meta, ensure_ascii=False),
                 json.dumps([float(x) for x in vec]), int(vec.size), now),
            )
            ids.append(chunk_id)
        conn.commit()
        return _ok(ids, f"写入 {len(ids)} 个切片到 {name}")
    finally:
        conn.close()


async def _search(data: dict) -> Dict[str, Any]:
    fn = "async_search_rag_sqlite"
    search_cfg = data.get("search_config") or {}
    try:
        top_k = max(1, min(int(search_cfg.get("top_k", 10)), 200))
    except (TypeError, ValueError):
        return _err("top_k 必须是整数", fn)
    threshold = search_cfg.get("score_threshold")
    doc_id = search_cfg.get("doc_id")

    qv = await async_get_query_vector(data)
    if qv.get("code") != 200:
        return qv
    query = _as_vector(qv["data"])

    db_file, name = _target(data)
    if not os.path.isfile(db_file):
        return _ok([], f"集合 {name} 不存在或为空")
    conn = _connect(db_file)
    try:
        sql = f"SELECT id, doc_id, chunk_index, text, metadata, embedding, dimension FROM {_TABLE}"
        params: list[Any] = []
        if doc_id:
            sql += " WHERE doc_id=?"
            params.append(str(doc_id))
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if not rows:
        return _ok([], "未命中")

    dims = {r["dimension"] for r in rows}
    if len(dims) > 1:
        return _err(f"集合 {name} 内存在多种向量维度 {sorted(dims)}，请重建集合", fn)
    if query.size != rows[0]["dimension"]:
        return _err(f"查询向量维度 {query.size} 与集合维度 {rows[0]['dimension']} 不一致", fn)

    matrix = np.vstack([_as_vector(json.loads(r["embedding"])) for r in rows])
    scores = _cosine(query, matrix)
    order = np.argsort(-scores)
    hits = []
    for idx in order:
        score = float(scores[idx])
        if threshold is not None:
            try:
                if score < float(threshold):
                    continue
            except (TypeError, ValueError):
                return _err("score_threshold 必须是数字", fn)
        r = rows[int(idx)]
        meta = json.loads(r["metadata"] or "{}")
        hits.append({
            "id": r["id"],
            "text": r["text"],
            "metadata": meta,
            "score": score,
        })
        if len(hits) >= top_k:
            break
    return _ok(hits, f"命中 {len(hits)} 条")


def _delete(data: dict) -> Dict[str, Any]:
    fn = "async_delete_rag_sqlite"
    doc_id = str((data.get("delete_config") or {}).get("doc_id") or "").strip()
    if not doc_id:
        return _err("缺少 delete_config.doc_id", fn)
    db_file, name = _target(data)
    if not os.path.isfile(db_file):
        return _ok(doc_id, f"集合 {name} 不存在")
    conn = _connect(db_file)
    try:
        cur = conn.execute(f"DELETE FROM {_TABLE} WHERE doc_id=?", (doc_id,))
        conn.commit()
        return _ok(doc_id, f"已删除 {cur.rowcount} 个切片")
    finally:
        conn.close()


def _delete_collection(data: dict) -> Dict[str, Any]:
    fn = "async_delete_collection_sqlite"
    db_file, name = _target(data)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(db_file + suffix)
        except FileNotFoundError:
            pass
        except OSError as e:
            return _err(f"删除集合失败：{e}", fn, code=500)
    return _ok(name, f"集合 {name} 已删除")


def _list(data: dict) -> Dict[str, Any]:
    rag_cfg = data.get("rag_config") or {}
    cfg = rag_cfg.get("sqlite_config") or {}
    base_dir = os.path.abspath(str(cfg.get("base_dir") or os.path.join(os.getcwd(), "rag_db")))
    if not os.path.isdir(base_dir):
        return _ok([], "暂无集合")
    names = sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(base_dir)
        if f.endswith(".db") and not f.startswith(".")
    )
    return _ok(names, f"共 {len(names)} 个集合")


async def async_write_rag_sqlite(data: dict) -> Dict[str, Any]:
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", "async_write_rag_sqlite")
        return await _write(data)
    except (TypeError, ValueError) as e:
        return _err(str(e), "async_write_rag_sqlite")
    except Exception as e:
        return _err(f"写入失败：{type(e).__name__}: {e}", "async_write_rag_sqlite", code=500)


async def async_search_rag_sqlite(data: dict) -> Dict[str, Any]:
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", "async_search_rag_sqlite")
        return await _search(data)
    except (TypeError, ValueError) as e:
        return _err(str(e), "async_search_rag_sqlite")
    except Exception as e:
        return _err(f"检索失败：{type(e).__name__}: {e}", "async_search_rag_sqlite", code=500)


async def async_delete_rag_sqlite(data: dict) -> Dict[str, Any]:
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", "async_delete_rag_sqlite")
        return _delete(data)
    except (TypeError, ValueError) as e:
        return _err(str(e), "async_delete_rag_sqlite")
    except Exception as e:
        return _err(f"删除失败：{type(e).__name__}: {e}", "async_delete_rag_sqlite", code=500)


async def async_delete_collection_sqlite(data: dict) -> Dict[str, Any]:
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", "async_delete_collection_sqlite")
        return _delete_collection(data)
    except (TypeError, ValueError) as e:
        return _err(str(e), "async_delete_collection_sqlite")
    except Exception as e:
        return _err(f"删除集合失败：{type(e).__name__}: {e}",
                    "async_delete_collection_sqlite", code=500)


async def async_list_rag_sqlite(data: dict) -> Dict[str, Any]:
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", "async_list_rag_sqlite")
        return _list(data)
    except (TypeError, ValueError) as e:
        return _err(str(e), "async_list_rag_sqlite")
    except Exception as e:
        return _err(f"列出集合失败：{type(e).__name__}: {e}", "async_list_rag_sqlite", code=500)


async def async_list_documents_rag_sqlite(data: dict) -> Dict[str, Any]:
    """列出集合内的文档（按 doc_id 聚合）。"""
    fn = "async_list_documents_rag_sqlite"
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", fn)
        db_file, name = _target(data)
        if not os.path.isfile(db_file):
            return _ok([], f"集合 {name} 不存在或为空")
        conn = _connect(db_file)
        try:
            rows = conn.execute(
                f"SELECT doc_id, text, metadata FROM {_TABLE} ORDER BY doc_id, chunk_index"
            ).fetchall()
        finally:
            conn.close()
        docs: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            item = docs.setdefault(r["doc_id"], {
                "document_id": r["doc_id"],
                "source": r["doc_id"],
                "chunk_count": 0,
                "metadata": json.loads(r["metadata"] or "{}"),
            })
            item["chunk_count"] += 1
        return _ok(list(docs.values()), f"共 {len(docs)} 个文档")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"列出文档失败：{type(e).__name__}: {e}", fn, code=500)


__all__ = [
    "async_write_rag_sqlite",
    "async_search_rag_sqlite",
    "async_delete_rag_sqlite",
    "async_delete_collection_sqlite",
    "async_list_rag_sqlite",
    "async_list_documents_rag_sqlite",
]
