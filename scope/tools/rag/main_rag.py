# -*- coding: utf-8 -*-
"""RAG 工具统一入口。

把 ``scope/rag`` 的知识库能力包装成 Agent 可调用的函数工具：

    write / read / delete / delete_collection / list

数据契约与其余工具一致：业务参数平铺在 data 顶层，返回
``{"code": 200|400|500, "data": ..., "message": ...}``。
"""

from __future__ import annotations

import os
from typing import Any, Dict

try:  # scope.tools.rag 包导入
    from ...rag.rag_main import async_rag_config
except ImportError:  # 顶层 tools 导入（scope/ 在 sys.path）
    from rag.rag_main import async_rag_config


FUNCTIONS = ("write", "read", "search", "delete", "delete_collection",
             "list", "documents", "list_documents")


def _err(message: str, fn: str = "async_rag_tools") -> Dict[str, Any]:
    return {"code": 400, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


async def async_rag_tools(data: dict = None) -> Dict[str, Any]:
    """知识库检索与管理工具。

    公共配置段 ``rag_config``:
        type(str, 默认 sqlite)     向量库类型；当前支持 sqlite
        sqlite_config(dict)        {"path": 集合名, "base_dir": 数据目录}
        vector_type(str)           dense（sqlite 后端仅支持 dense）
        rag_function(str)          通常由 function 自动填入

    功能与业务参数:
        write  文件解析 → 切片 → embedding → 入库
               file_config(dict): file_path / file_name / is_bytes / bytes / ...
               file_chunker(dict): chunk_size(默认 256) / overlap(默认 0)
               embedding(dict): 向量模型配置；也可传 embedding_model 对象
        read / search  检索
               query(str, 必填)
               top_k(int, 默认 10)
               doc_id(str, 可选) 限定文档
               score_threshold(float, 可选)
               embedding(dict) 或 embedding_model
        delete  删除单个文档
               doc_id(str, 必填)
        delete_collection  删除整个集合
        list    列出集合
        documents / list_documents  列出集合内文档（按 doc_id 聚合）

    示例::

        await async_rag_tools({
            "function": "read",
            "rag_config": {"type": "sqlite", "sqlite_config": {"path": "kb"}},
            "query": "如何部署",
            "top_k": 5,
            "embedding": {"provider": "openai", "model": "...", "api_key": "..."},
        })
    """
    if not isinstance(data, dict):
        return _err(f"data 必须是字典对象，收到 {type(data).__name__}")
    function = str(data.get("function") or "").strip().lower()
    if function not in FUNCTIONS:
        return _err(f"未知 function: {function or '(空)'}，支持: {', '.join(FUNCTIONS)}")

    rag_config = dict(data.get("rag_config") or {})
    rag_config["rag_function"] = "read" if function == "search" else function
    payload = dict(data)
    payload["rag_config"] = rag_config

    if function in ("read", "search"):
        search_config = dict(data.get("search_config") or {})
        for key in ("query", "top_k", "doc_id", "score_threshold"):
            if data.get(key) is not None:
                search_config[key] = data[key]
        payload["search_config"] = search_config
        if data.get("embedding") is not None:
            payload["embedding"] = data["embedding"]
        if data.get("embedding_model") is not None:
            payload["embedding_model"] = data["embedding_model"]

    if function == "delete":
        delete_config = dict(data.get("delete_config") or {})
        if data.get("doc_id") is not None:
            delete_config["doc_id"] = data["doc_id"]
        payload["delete_config"] = delete_config

    return await async_rag_config(payload)


__all__ = ["async_rag_tools"]
