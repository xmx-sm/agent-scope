"""知识库（RAG）服务：直接调用 scope RAG API。"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.database import AsyncSessionLocal
from app.services.agent.runtime.scope_bridge import ROOT
from app.services.access.tools.tool_config import async_effective as async_tool_config

RAG_ROOT = ROOT / "backend" / "uploads" / "agents"


def _base_dir(user_id: str) -> str:
    """内部辅助函数：_base_dir。
    参数：user_id。
    """
    path = RAG_ROOT / f"user_{user_id}" / "rag"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


async def _embedding(session: AsyncSession, user_id: str) -> dict:
    """读取用户级 Embedding 配置（工具配置可覆盖，默认跟随系统 Agent 配置）。"""
    cfg = await async_tool_config(
        {"session": session, "user_id": user_id, "category": "embedding"}
    )
    provider = str(cfg.get("provider") or "").strip()
    model = str(cfg.get("model") or "").strip()
    if not provider or not model:
        raise ApiError("请先在工具配置 → Embedding 或 Agent 配置中填写 Embedding 服务商与模型")
    result = {
        "provider": provider,
        "model": model,
        "base_url": str(cfg.get("base_url") or ""),
        "api_key": str(cfg.get("api_key") or ""),
    }
    dimensions = int(cfg.get("dimensions") or 0)
    if dimensions:
        result["dimensions"] = dimensions
    return result


def _rag_config(user_id: str, collection: str) -> dict:
    """内部辅助函数：_rag_config。
    参数：user_id / collection。
    """
    return {
        "type": "sqlite",
        "sqlite_config": {"path": collection or "default", "base_dir": _base_dir(user_id)},
        "vector_type": "dense",
    }


async def _call(payload: dict) -> dict:
    """内部辅助函数：_call。
    参数：payload。
    """
    from scope.tools.rag.main_rag import async_rag_tools

    result = await async_rag_tools(payload)
    if result.get("code") != 200:
        raise ApiError(result.get("message") or "知识库操作失败")
    return result.get("data")


async def async_libraries(params: dict) -> list:
    """列出旧版 RAG 向量库。

        参数：session / user_id。
        """
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    return await _call(
        {
            "function": "list",
            "rag_config": _rag_config(user_id, "default"),
        }
    )


async def async_documents(params: dict) -> list:
    """列出旧版 RAG 文档。

        参数：collection / session / user_id。
        """
    session: AsyncSession = params["session"]
    return await _call(
        {
            "function": "documents",
            "rag_config": _rag_config(params["user_id"], params.get("collection") or "default"),
        }
    )


async def async_upload(params: dict) -> dict:
    """上传旧版 RAG 文档。

        参数：collection / filename / session / user_id / content。
        """
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    collection = str(params.get("collection") or "default")
    filename = str(params.get("filename") or "file")
    content: bytes = params["content"]
    embedding = await _embedding(session, user_id)
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
    """旧版 RAG 检索。

        参数：collection / top_k / session / user_id / query。
        """
    session: AsyncSession = params["session"]
    embedding = await _embedding(session, params["user_id"])
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
    """删除旧版 RAG 文档。

        参数：collection / session / user_id / doc_id。
        """
    session: AsyncSession = params["session"]
    return await _call(
        {
            "function": "delete",
            "rag_config": _rag_config(params["user_id"], params.get("collection") or "default"),
            "doc_id": params["doc_id"],
        }
    )


async def async_delete_library(params: dict) -> dict:
    """删除旧版 RAG 向量库。

        参数：session / user_id / collection。
        """
    session: AsyncSession = params["session"]
    return await _call(
        {
            "function": "delete_collection",
            "rag_config": _rag_config(params["user_id"], params["collection"]),
        }
    )
