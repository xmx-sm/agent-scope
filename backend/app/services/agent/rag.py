"""知识库（RAG）服务：直接调用 scope RAG API。"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.database import AsyncSessionLocal
from app.services.agent.scope_bridge import ROOT
from app.services.config.service import async_get_config

RAG_ROOT = ROOT / "backend" / "uploads" / "agents"


def _base_dir(user_id: str) -> str:
    path = RAG_ROOT / f"user_{user_id}" / "rag"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


async def _embedding(session: AsyncSession) -> dict:
    async def get(key: str, default=""):
        return await async_get_config({"session": session, "key": key, "default": default})

    provider = str(await get("ai.embedding.provider", "") or "")
    model = str(await get("ai.embedding.model", "") or "")
    base_url = str(await get("ai.embedding.base_url", "") or "")
    api_key = str(await get("ai.embedding.api_key", "") or "")
    dimensions = int(await get("ai.embedding.dimensions", 0) or 0)
    if not provider or not model:
        raise ApiError("请先在 Agent 配置中填写 Embedding 服务商与模型")
    cfg = {"provider": provider, "model": model, "base_url": base_url, "api_key": api_key}
    if dimensions:
        cfg["dimensions"] = dimensions
    return cfg


def _rag_config(user_id: str, collection: str) -> dict:
    return {
        "type": "sqlite",
        "sqlite_config": {"path": collection or "default", "base_dir": _base_dir(user_id)},
        "vector_type": "dense",
    }


async def _call(payload: dict) -> dict:
    from scope.tools.rag.main_rag import async_rag_tools

    result = await async_rag_tools(payload)
    if result.get("code") != 200:
        raise ApiError(result.get("message") or "知识库操作失败")
    return result.get("data")


async def async_libraries(params: dict) -> list:
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    return await _call(
        {
            "function": "list",
            "rag_config": _rag_config(user_id, "default"),
        }
    )


async def async_documents(params: dict) -> list:
    session: AsyncSession = params["session"]
    return await _call(
        {
            "function": "documents",
            "rag_config": _rag_config(params["user_id"], params.get("collection") or "default"),
        }
    )


async def async_upload(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    collection = str(params.get("collection") or "default")
    filename = str(params.get("filename") or "file")
    content: bytes = params["content"]
    embedding = await _embedding(session)
    extension = Path(filename).suffix.lstrip(".").lower()
    data = await _call(
        {
            "function": "write",
            "rag_config": _rag_config(user_id, collection),
            "file_config": {
                "is_bytes": True,
                "bytes": content,
                "file_name": filename,
                "file_extension": extension,
            },
            "file_chunker": {"chunk_size": 256, "overlap": 0},
            "embedding": embedding,
        }
    )
    return {"collection": collection, "result": data}


async def async_search(params: dict) -> list:
    session: AsyncSession = params["session"]
    embedding = await _embedding(session)
    return await _call(
        {
            "function": "read",
            "rag_config": _rag_config(params["user_id"], params.get("collection") or "default"),
            "search_config": {
                "query": params["query"],
                "top_k": int(params.get("top_k") or 5),
            },
            "embedding": embedding,
        }
    )


async def async_delete_document(params: dict) -> dict:
    session: AsyncSession = params["session"]
    return await _call(
        {
            "function": "delete",
            "rag_config": _rag_config(params["user_id"], params.get("collection") or "default"),
            "doc_id": params["doc_id"],
        }
    )


async def async_delete_library(params: dict) -> dict:
    session: AsyncSession = params["session"]
    return await _call(
        {
            "function": "delete_collection",
            "rag_config": _rag_config(params["user_id"], params["collection"]),
        }
    )
