# -*- coding: utf-8 -*-
"""官方 KnowledgeBase / RAGMiddleware 构建器。

把 SQLite 向量库、embedding 模型和知识库配置组装成：

- ``agentscope.rag.KnowledgeBase``
- ``agentscope.middleware.RAGMiddleware``

之后直接传给 ``Agent(middlewares=[middleware], ...)`` 即可：

- ``mode="agentic"``：暴露 ``search_knowledge`` 工具，由模型决定何时检索
- ``mode="static"``：每轮用户输入自动检索并注入 HintBlock

配置示例::

    r = await async_create_rag_middleware({
        "knowledge_bases": [
            {
                "name": "handbook",
                "description": "公司制度与流程",
                "collection": "handbook",
                "sqlite_config": {"base_dir": "/data/rag_db"},
                "metadata_filter": {"tenant_id": "t1"},
                "embedding": {"provider": "openai", "model": "...", "api_key": "..."},
            }
        ],
        "search_config": {"mode": "agentic", "top_k": 5},
    })
    middleware = r["data"]["middleware"]
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agentscope.middleware import RAGMiddleware
from agentscope.rag import KnowledgeBase

try:  # 顶层 rag 导入
    from config import get as _cfg_get
except ImportError:  # scope.rag 包导入
    from scope.config import get as _cfg_get

try:
    from ..llm.agent_model import async_get_embedding_model, async_get_llm_model
except ImportError:
    from llm.agent_model import async_get_embedding_model, async_get_llm_model

from .vector_store_factory import async_create_vector_store, ZvecKnowledgeBase
from ._utils import as_bool, as_dict


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _embedding_cfg(data: dict, item: dict) -> Dict[str, Any]:
    """item.embedding > data.embedding > config.db rag.embedding.*。"""
    cfg: Dict[str, Any] = {}
    for key in ("provider", "model", "base_url", "api_key", "dimensions", "batch_size"):
        v = _cfg_get(f"rag.embedding.{key}", None)
        if v is not None:
            cfg[key] = v
    if isinstance(data.get("embedding"), dict):
        cfg.update(data["embedding"])
    if isinstance(item.get("embedding"), dict):
        cfg.update(item["embedding"])
    return cfg


def _base_dir(data: dict, item: dict) -> str:
    for source in (item.get("sqlite_config"), data.get("sqlite_config")):
        if source is not None and not isinstance(source, dict):
            raise ValueError("sqlite_config 必须是字典")
        if isinstance(source, dict) and source.get("base_dir"):
            path = str(source["base_dir"])
            if not os.path.isabs(path):
                raise ValueError(f"sqlite_config.base_dir 必须是绝对路径: {path}")
            return os.path.abspath(path)
    configured = _cfg_get("rag.sqlite.base_dir", None)
    if configured:
        return os.path.abspath(str(configured))
    raise ValueError("缺少参数 sqlite_config.base_dir（或 config.db 的 rag.sqlite.base_dir）")


def _create_dir(data: dict, item: dict) -> bool:
    for source in (item, data):
        if source.get("create_dir") is not None:
            return as_bool(source["create_dir"], "create_dir", default=False)
    for source in (item.get("sqlite_config"), data.get("sqlite_config")):
        if isinstance(source, dict) and source.get("create_dir") is not None:
            return as_bool(source["create_dir"], "create_dir", default=False)
    return as_bool(_cfg_get("rag.sqlite.create_dir", False), "create_dir", default=False)


async def _embedding_model(data: dict, item: dict) -> Dict[str, Any]:
    injected = item.get("embedding_model") or data.get("embedding_model")
    if injected is not None:
        return _ok(injected)
    cfg = _embedding_cfg(data, item)
    if not cfg:
        return _err("缺少 embedding 配置（或传入 embedding_model 对象）",
                    "async_create_rag_middleware")
    return await async_get_embedding_model({"embedding": cfg})


async def async_create_knowledge_base(data: dict = None) -> Dict[str, Any]:
    """构建单个 KnowledgeBase。"""
    fn = "async_create_knowledge_base"
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", fn)
        item = data.get("knowledge_base")
        if not isinstance(item, dict):
            return _err("缺少 knowledge_base 配置段", fn)
        name = str(item.get("name") or "").strip()
        if not name:
            return _err("缺少 knowledge_base.name", fn)

        store_r = await async_create_vector_store(data, item)
        if store_r.get("code") != 200:
            return store_r
        store_data = store_r["data"]
        store = store_data["store"]
        backend = store_data["backend"]
        zvec_cfg = store_data.get("config") or {}
        zvec_mode = str(zvec_cfg.get("mode") or "hybrid").lower()

        embedding_model = None
        if not (backend == "zvec" and zvec_mode == "bm25"):
            emb = await _embedding_model(data, item)
            if emb.get("code") != 200:
                return emb
            embedding_model = emb["data"]

        kb_cls = store_data.get("knowledge_base") or KnowledgeBase
        kb_kwargs = {}
        if kb_cls is ZvecKnowledgeBase:
            kb_kwargs["zvec_mode"] = zvec_mode
        await store.__aenter__()
        kb = kb_cls(
            name=name,
            description=str(item.get("description") or name),
            embedding_model=embedding_model,
            vector_store=store,
            collection=str(item.get("collection") or name),
            metadata_filter=item.get("metadata_filter") or None,
            **kb_kwargs,
        )
        return _ok({"knowledge_base": kb, "vector_store": store,
                    "backend": backend},
                   "KnowledgeBase 创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"KnowledgeBase 创建失败：{type(e).__name__}: {e}", fn, code=500)


def _middleware_parameters(search_config: dict) -> RAGMiddleware.Parameters:
    fields = set(RAGMiddleware.Parameters.model_fields)
    values = {k: v for k, v in (search_config or {}).items() if k in fields}
    return RAGMiddleware.Parameters(**values)


async def async_create_rag_middleware(data: dict = None) -> Dict[str, Any]:
    """构建 RAGMiddleware（可带多个 KnowledgeBase）。

    入参:
        knowledge_bases(list, 二选一)  每个元素同 knowledge_base 配置
        knowledge_base(dict, 二选一)   单个知识库配置
        embedding(dict, 可选)          全局 embedding 配置
        embedding_model(对象, 可选)    全局注入的 embedding 模型
        search_config(dict, 可选)      RAGMiddleware.Parameters 字段
        rerank_model(对象或 dict, 可选) 可选的 rerank ChatModel；dict 走模型工厂
    """
    fn = "async_create_rag_middleware"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", fn)

        items = data.get("knowledge_bases")
        if items is None:
            if isinstance(data.get("knowledge_base"), dict):
                items = [data["knowledge_base"]]
            else:
                items = []
        if not isinstance(items, list) or not items:
            return _err("缺少 knowledge_bases 配置段", fn)

        kbs: List[KnowledgeBase] = []
        stores = []
        for item in items:
            if not isinstance(item, dict):
                return _err("knowledge_bases 元素必须是字典", fn)
            r = await async_create_knowledge_base({**data, "knowledge_base": item})
            if r.get("code") != 200:
                return r
            kbs.append(r["data"]["knowledge_base"])
            stores.append(r["data"]["vector_store"])

        try:
            parameters = _middleware_parameters(data.get("search_config") or {})
        except Exception as e:
            return _err(f"search_config 非法：{e}", fn)

        rerank_model = data.get("rerank_model")
        if isinstance(rerank_model, dict):
            cfg = rerank_model.get("llm") if isinstance(
                rerank_model.get("llm"), dict) else rerank_model
            rr = await async_get_llm_model({"llm": cfg})
            if rr.get("code") != 200:
                return _err(
                    f"rerank_model 初始化失败：{rr.get('message')}", fn)
            rerank_model = rr["data"]

        middleware = RAGMiddleware(
            knowledge_bases=kbs,
            parameters=parameters,
            rerank_model=rerank_model,
        )
        return _ok({"middleware": middleware, "knowledge_bases": kbs,
                    "vector_stores": stores}, "RAGMiddleware 创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"RAGMiddleware 创建失败：{type(e).__name__}: {e}", fn, code=500)


__all__ = ["async_create_knowledge_base", "async_create_rag_middleware"]
