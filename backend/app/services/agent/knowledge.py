"""知识库：向量库、文档、解析、检索、日志。"""

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import VectorDocument, VectorLibrary, VectorLog
from app.services.agent.scope_bridge import ROOT
from app.services.config.service import async_get_config

LIBRARY_ROOT = ROOT / "backend" / "uploads" / "agents"
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fa5]{1,64}$")


def _library_dir(user_id: str, name: str) -> Path:
    return LIBRARY_ROOT / f"user_{user_id}" / "libraries" / name


async def _system_embedding(session: AsyncSession) -> dict:
    async def get(key: str, default=""):
        return await async_get_config({"session": session, "key": key, "default": default})

    provider = str(await get("ai.embedding.provider", "") or "")
    model = str(await get("ai.embedding.model", "") or "")
    if not provider or not model:
        raise ApiError("请先在默认配置 → Agent 配置中填写 Embedding 服务商与模型")
    cfg = {
        "provider": provider,
        "model": model,
        "base_url": str(await get("ai.embedding.base_url", "") or ""),
        "api_key": str(await get("ai.embedding.api_key", "") or ""),
    }
    dimensions = int(await get("ai.embedding.dimensions", 0) or 0)
    if dimensions:
        cfg["dimensions"] = dimensions
    return cfg


def _rag_config(library: VectorLibrary) -> dict:
    root = _library_dir(library.user_id, library.name)
    root.mkdir(parents=True, exist_ok=True)
    config = {}
    try:
        config = json.loads(library.config or "{}")
    except (ValueError, TypeError):
        config = {}
    if library.vector_type == "sqlite":
        return {
            "type": "sqlite",
            "sqlite_config": {"path": library.name, "base_dir": str(root)},
            "vector_type": config.get("vector_type", "dense"),
        }
    return {
        "type": library.vector_type,
        f"{library.vector_type}_config": {
            "path": library.name,
            "base_dir": str(root),
            **config,
        },
    }


async def _embedding(session: AsyncSession, library: VectorLibrary) -> dict:
    try:
        explicit = json.loads(library.embedding or "{}")
    except (ValueError, TypeError):
        explicit = {}
    if explicit.get("provider") and explicit.get("model"):
        return explicit
    return await _system_embedding(session)


async def _call(payload: dict) -> dict:
    from scope.tools.rag.main_rag import async_rag_tools

    result = await async_rag_tools(payload)
    if result.get("code") != 200:
        raise ApiError(result.get("message") or "知识库操作失败")
    return result


async def _log(session: AsyncSession, *, user_id: str, operation: str, status: str,
               library_id: str | None = None, document_id: str | None = None,
               details: dict | None = None, error: str = "") -> None:
    session.add(
        VectorLog(
            user_id=user_id,
            library_id=library_id,
            document_id=document_id,
            operation=operation,
            status=status,
            details=json.dumps(details or {}, ensure_ascii=False),
            error_message=error[:2000],
        )
    )


def _public_library(row: VectorLibrary) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "vector_type": row.vector_type,
        "description": row.description,
        "embedding": json.loads(row.embedding or "{}"),
        "config": json.loads(row.config or "{}"),
        "status": row.status,
        "origin": row.origin,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def async_libraries(params: dict) -> list[dict]:
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    rows = (
        await session.execute(
            select(VectorLibrary).where(VectorLibrary.user_id == user_id).order_by(VectorLibrary.name)
        )
    ).scalars().all()
    result = []
    for row in rows:
        item = _public_library(row)
        count = (
            await session.execute(
                select(VectorDocument).where(VectorDocument.library_id == row.id)
            )
        ).scalars().all()
        item["document_count"] = len(count)
        item["chunk_count"] = sum(doc.chunk_count for doc in count)
        result.append(item)
    return result


async def async_library_create(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    data: dict = params["data"]
    name = str(data.get("name") or "").strip()
    if not _NAME_RE.match(name):
        raise ApiError("库名只支持中英文、数字、下划线、短横线，长度 1-64")
    exists = (
        await session.execute(
            select(VectorLibrary).where(
                VectorLibrary.user_id == user_id, VectorLibrary.name == name
            )
        )
    ).scalar_one_or_none()
    if exists:
        raise ApiError("库名已存在")
    vector_type = str(data.get("vector_type") or "sqlite")
    row = VectorLibrary(
        user_id=user_id,
        name=name,
        vector_type=vector_type,
        description=str(data.get("description") or ""),
        embedding=json.dumps(data.get("embedding") or {}, ensure_ascii=False),
        config=json.dumps(data.get("config") or {}, ensure_ascii=False),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _public_library(row)


async def async_library_update(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = await session.get(VectorLibrary, params["library_id"])
    if row is None or row.user_id != params["user_id"]:
        raise ApiError("向量库不存在", code=404)
    data: dict = params["data"]
    if data.get("description") is not None:
        row.description = str(data["description"])
    if data.get("embedding") is not None:
        row.embedding = json.dumps(data["embedding"], ensure_ascii=False)
    if data.get("config") is not None:
        row.config = json.dumps(data["config"], ensure_ascii=False)
    if data.get("status") in ("active", "inactive"):
        row.status = data["status"]
    await session.commit()
    await session.refresh(row)
    return _public_library(row)


async def async_library_delete(params: dict) -> None:
    session: AsyncSession = params["session"]
    row = await session.get(VectorLibrary, params["library_id"])
    if row is None or row.user_id != params["user_id"]:
        raise ApiError("向量库不存在", code=404)
    try:
        await _call(
            {"function": "delete_collection", "rag_config": _rag_config(row)}
        )
    except Exception as exc:  # noqa: BLE001
        await _log(session, user_id=row.user_id, library_id=row.id,
                   operation="delete_collection", status="failed", error=str(exc))
    docs = (
        await session.execute(
            select(VectorDocument).where(VectorDocument.library_id == row.id)
        )
    ).scalars().all()
    for doc in docs:
        await session.delete(doc)
    shutil.rmtree(_library_dir(row.user_id, row.name), ignore_errors=True)
    await session.delete(row)
    await session.commit()


async def async_library_rebuild(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = await session.get(VectorLibrary, params["library_id"])
    if row is None or row.user_id != params["user_id"]:
        raise ApiError("向量库不存在", code=404)
    try:
        await _call({"function": "delete_collection", "rag_config": _rag_config(row)})
    except Exception:  # noqa: BLE001
        pass
    docs = (
        await session.execute(
            select(VectorDocument).where(VectorDocument.library_id == row.id)
        )
    ).scalars().all()
    for doc in docs:
        doc.status = "pending"
        doc.chunk_count = 0
        doc.error_message = ""
    await _log(session, user_id=row.user_id, library_id=row.id,
               operation="rebuild_index", status="success", details={"documents": len(docs)})
    await session.commit()
    return {"library_id": row.id, "pending_documents": len(docs)}


async def async_library_test(params: dict) -> dict:
    session: AsyncSession = params["session"]
    row = await session.get(VectorLibrary, params["library_id"])
    if row is None or row.user_id != params["user_id"]:
        raise ApiError("向量库不存在", code=404)
    data = await _call({"function": "list", "rag_config": _rag_config(row)})
    return {"library_id": row.id, "collections": data}


async def async_upload_document(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    library = await session.get(VectorLibrary, params["library_id"])
    if library is None or library.user_id != user_id:
        raise ApiError("向量库不存在", code=404)
    filename = Path(params.get("filename") or "file").name
    content: bytes = params["content"]
    if len(content) > 50 * 1024 * 1024:
        raise ApiError("文档不能超过 50MB")
    source_dir = _library_dir(user_id, library.name) / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    stored = source_dir / f"{uuid.uuid4().hex[:8]}_{filename}"
    stored.write_bytes(content)
    row = VectorDocument(
        user_id=user_id,
        library_id=library.id,
        filename=filename,
        source_path=str(stored),
        status="pending",
        filesize=len(content),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _public_document(row)


def _public_document(row: VectorDocument) -> dict:
    return {
        "id": row.id,
        "library_id": row.library_id,
        "filename": row.filename,
        "status": row.status,
        "chunk_count": row.chunk_count,
        "filesize": row.filesize,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "parsed_at": row.parsed_at.isoformat() if row.parsed_at else None,
    }


async def async_documents(params: dict) -> dict:
    session: AsyncSession = params["session"]
    stmt = select(VectorDocument).where(VectorDocument.user_id == params["user_id"])
    if params.get("library_id"):
        stmt = stmt.where(VectorDocument.library_id == params["library_id"])
    if params.get("status"):
        stmt = stmt.where(VectorDocument.status == params["status"])
    rows = (await session.execute(stmt.order_by(VectorDocument.created_at.desc()))).scalars().all()
    return {"documents": [_public_document(row) for row in rows], "total": len(rows)}


async def async_parse_document(params: dict) -> dict:
    session: AsyncSession = params["session"]
    doc = await session.get(VectorDocument, params["document_id"])
    if doc is None or doc.user_id != params["user_id"]:
        raise ApiError("文档不存在", code=404)
    library = await session.get(VectorLibrary, doc.library_id)
    if library is None:
        raise ApiError("向量库不存在", code=404)
    doc.status = "parsing"
    await session.commit()
    try:
        embedding = await _embedding(session, library)
        config = json.loads(library.config or "{}")
        result = await _call(
            {
                "function": "write",
                "rag_config": _rag_config(library),
                "file_config": {
                    "file_path": doc.source_path,
                    "file_name": Path(doc.source_path).name,
                },
                "file_chunker": {
                    "chunk_size": int(config.get("chunk_size") or 256),
                    "overlap": int(config.get("overlap") or 0),
                },
                "embedding": embedding,
            }
        )
        chunks = result.get("data") or []
        doc.status = "parsed"
        doc.chunk_count = len(chunks) if isinstance(chunks, list) else 0
        doc.error_message = ""
        doc.parsed_at = datetime.now(timezone.utc)
        await _log(
            session, user_id=doc.user_id, library_id=library.id, document_id=doc.id,
            operation="parse", status="success",
            details={"chunks": doc.chunk_count},
        )
    except Exception as exc:  # noqa: BLE001
        doc.status = "failed"
        doc.error_message = str(exc)[:2000]
        await _log(
            session, user_id=doc.user_id, library_id=library.id, document_id=doc.id,
            operation="parse", status="failed", error=str(exc),
        )
    await session.commit()
    await session.refresh(doc)
    if doc.status == "failed":
        raise ApiError(f"解析失败：{doc.error_message}")
    return _public_document(doc)


async def async_delete_document(params: dict) -> None:
    session: AsyncSession = params["session"]
    doc = await session.get(VectorDocument, params["document_id"])
    if doc is None or doc.user_id != params["user_id"]:
        raise ApiError("文档不存在", code=404)
    library = await session.get(VectorLibrary, doc.library_id)
    if library is not None:
        try:
            await _call(
                {
                    "function": "delete",
                    "rag_config": _rag_config(library),
                    "doc_id": Path(doc.source_path).name,
                }
            )
        except Exception:  # noqa: BLE001
            pass
    Path(doc.source_path).unlink(missing_ok=True)
    await _log(session, user_id=doc.user_id, library_id=doc.library_id,
               document_id=doc.id, operation="delete", status="success")
    await session.delete(doc)
    await session.commit()


async def async_search(params: dict) -> dict:
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    libraries = []
    if params.get("library_ids"):
        rows = (
            await session.execute(
                select(VectorLibrary).where(
                    VectorLibrary.user_id == user_id,
                    VectorLibrary.id.in_(params["library_ids"]),
                )
            )
        ).scalars().all()
        libraries = list(rows)
    else:
        libraries = list(
            (
                await session.execute(
                    select(VectorLibrary).where(
                        VectorLibrary.user_id == user_id,
                        VectorLibrary.status == "active",
                    )
                )
            ).scalars().all()
        )
    results = []
    errors = []
    for library in libraries:
        try:
            embedding = await _embedding(session, library)
            data = await _call(
                {
                    "function": "read",
                    "rag_config": _rag_config(library),
                    "search_config": {
                        "query": params["query"],
                        "top_k": int(params.get("top_k") or 5),
                        "score_threshold": params.get("score_threshold"),
                    },
                    "embedding": embedding,
                }
            )
            items = data if isinstance(data, list) else (data or {}).get("results") or []
            for item in items:
                if isinstance(item, dict):
                    item["library_name"] = library.name
                    item["library_id"] = library.id
            results.extend(items)
        except Exception as exc:  # noqa: BLE001
            errors.append({"library_id": library.id, "library_name": library.name, "error": str(exc)})
    results.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    await _log(session, user_id=user_id, operation="search", status="success",
               details={"query": params["query"], "hits": len(results),
                        "libraries": [lib.name for lib in libraries]})
    await session.commit()
    return {"results": results[: int(params.get("top_k") or 5) * max(1, len(libraries))],
            "errors": errors, "searched_libraries": [lib.name for lib in libraries]}


async def async_logs(params: dict) -> dict:
    session: AsyncSession = params["session"]
    stmt = select(VectorLog).where(VectorLog.user_id == params["user_id"])
    if params.get("library_id"):
        stmt = stmt.where(VectorLog.library_id == params["library_id"])
    rows = (await session.execute(stmt.order_by(VectorLog.created_at.desc()).limit(200))).scalars().all()
    return {
        "logs": [
            {
                "id": row.id,
                "library_id": row.library_id,
                "document_id": row.document_id,
                "operation": row.operation,
                "status": row.status,
                "details": row.details,
                "error_message": row.error_message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }
