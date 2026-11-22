# -*- coding: utf-8 -*-
"""RAG 参数解析：data > config.db > 代码默认 / 400。

与工具层口径一致：

- ``rag.type`` / ``rag.sqlite.path``：选择类参数，data 与 SQLite 都没有 → 400
- ``top_k`` / ``chunk_size`` / ``overlap`` / ``require_file``：data > sqlite > 代码默认
- ``embedding``：data["embedding"] > config.db 的 rag.embedding.* > 空
- ``base_dir``：data > sqlite > ``{cwd}/rag_db``（本地存储兜底）
"""

from __future__ import annotations

import os
from typing import Any, Dict

try:  # 顶层 rag 导入（scope/ 在 sys.path）
    from config import get as _cfg_get
except ImportError:  # scope.rag 包导入
    from scope.config import get as _cfg_get

from ._utils import as_bool, as_dict


def _merged_sqlite(data_cfg: dict, rag_type: str, data: dict) -> Dict[str, Any]:
    cfg = dict(as_dict(data_cfg.get("sqlite_config"), "sqlite_config"))
    if cfg.get("path") is None:
        cfg["path"] = _cfg_get("rag.sqlite.path", None)
    if not cfg.get("path"):
        raise ValueError("缺少参数 sqlite_config.path（调用未传且 config.db 未配置 rag.sqlite.path）")
    if not cfg.get("base_dir"):
        cfg["base_dir"] = _cfg_get("rag.sqlite.base_dir", None)
    if not cfg.get("base_dir"):
        raise ValueError(
            "缺少参数 sqlite_config.base_dir（调用未传且 config.db 未配置 rag.sqlite.base_dir）")
    base_dir = str(cfg["base_dir"])
    if not os.path.isabs(base_dir):
        raise ValueError(f"sqlite_config.base_dir 必须是绝对路径: {base_dir}")
    cfg["base_dir"] = os.path.abspath(base_dir)

    create_dir = data.get("create_dir")
    if create_dir is None:
        create_dir = cfg.get("create_dir")
    if create_dir is None:
        create_dir = _cfg_get("rag.sqlite.create_dir", False)
    cfg["create_dir"] = as_bool(create_dir, "create_dir", default=False)

    if not os.path.isdir(cfg["base_dir"]) and not cfg["create_dir"]:
        raise ValueError(
            f"RAG 数据目录不存在: {cfg['base_dir']}（如允许自动创建请传 create_dir=True）")
    return cfg


def _merged_embedding(data: dict) -> Dict[str, Any]:
    if data.get("embedding_model") is not None:
        return dict(data.get("embedding") or {})
    raw = data.get("embedding")
    cfg = dict(raw) if isinstance(raw, dict) else {}
    # config.db 只补缺失项，data 显式值优先
    for key in ("provider", "model", "base_url", "api_key", "dimensions", "batch_size"):
        if cfg.get(key) is None:
            v = _cfg_get(f"rag.embedding.{key}", None)
            if v is not None:
                cfg[key] = v
    return cfg


def resolve(data: dict = None) -> Dict[str, Any]:
    """返回归一化后的 data 副本；参数不足抛 ValueError。"""
    if not isinstance(data, dict):
        raise TypeError("data 必须是字典对象")

    rag_cfg = dict(as_dict(data.get("rag_config"), "rag_config"))
    rag_type = str(rag_cfg.get("type") or _cfg_get("rag.type", None) or "").strip().lower()
    if not rag_type:
        raise ValueError("缺少参数 rag_config.type（调用未传且 config.db 未配置 rag.type）")
    rag_cfg["type"] = rag_type

    vector_type = str(rag_cfg.get("vector_type") or _cfg_get("rag.vector_type", "dense")).lower()
    if rag_type == "sqlite" and vector_type != "dense":
        raise ValueError("SQLite 后端仅支持 vector_type=dense")
    rag_cfg["vector_type"] = vector_type

    if rag_type == "sqlite":
        rag_cfg["sqlite_config"] = _merged_sqlite(rag_cfg, rag_type, data)

    search = dict(as_dict(data.get("search_config"), "search_config"))
    if search.get("top_k") is None:
        try:
            search["top_k"] = int(_cfg_get("rag.top_k", 10))
        except (TypeError, ValueError):
            search["top_k"] = 10
    if search.get("score_threshold") is None:
        search["score_threshold"] = _cfg_get("rag.score_threshold", None)

    file_chunker = dict(as_dict(data.get("file_chunker"), "file_chunker"))
    if file_chunker.get("chunk_size") is None:
        try:
            file_chunker["chunk_size"] = int(_cfg_get("rag.chunk_size", 256))
        except (TypeError, ValueError):
            file_chunker["chunk_size"] = 256
    if file_chunker.get("overlap") is None:
        try:
            file_chunker["overlap"] = int(_cfg_get("rag.overlap", 0))
        except (TypeError, ValueError):
            file_chunker["overlap"] = 0

    file_config = dict(as_dict(data.get("file_config"), "file_config"))
    if "require_file" not in file_config:
        file_config["require_file"] = bool(_cfg_get("rag.require_file", True))

    out = dict(data)
    out["rag_config"] = rag_cfg
    out["search_config"] = search
    out["file_chunker"] = file_chunker
    out["file_config"] = file_config
    emb = _merged_embedding(data)
    if emb:
        out["embedding"] = emb
    return out


__all__ = ["resolve"]
