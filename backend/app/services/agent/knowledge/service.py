"""知识库：向量库、文档、切片、解析、共享、检索与日志。"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import (
    User,
    VectorChunk,
    VectorDocument,
    VectorLibrary,
    VectorLibraryShare,
    VectorLog,
)
from app.services.agent.runtime.scope_bridge import ROOT
from app.services.config.service import async_get_config
from app.utils.mask import SENTINEL

LIBRARY_ROOT = ROOT / "backend" / "uploads" / "agents"
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-一-龥]{1,64}$")


def _library_dir(user_id: str, name: str) -> Path:
    """内部辅助函数：_library_dir。
    参数：user_id / name。
    """
    return LIBRARY_ROOT / f"user_{user_id}" / "libraries" / name


async def _system_embedding(session: AsyncSession) -> dict:
    """内部辅助函数：_system_embedding。
    参数：session。
    """
    async def get(key: str, default=""):
        """读取系统配置。"""
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
    """内部辅助函数：_rag_config。
    参数：library。
    """
    root = _library_dir(library.user_id, library.name)
    root.mkdir(parents=True, exist_ok=True)
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
    """内部辅助函数：_embedding。
    参数：session / library。
    """
    try:
        explicit = json.loads(library.embedding or "{}")
    except (ValueError, TypeError):
        explicit = {}
    if explicit.get("provider") and explicit.get("model"):
        return explicit
    return await _system_embedding(session)


async def _call(payload: dict) -> dict:
    """内部辅助函数：_call。
    参数：payload。
    """
    from scope.tools.rag.main_rag import async_rag_tools

    result = await async_rag_tools(payload)
    if result.get("code") != 200:
        raise ApiError(result.get("message") or "知识库操作失败")
    return result


async def _log(
    session: AsyncSession,
    *,
    user_id: str,
    operation: str,
    status: str,
    library_id: str | None = None,
    document_id: str | None = None,
    details: dict | None = None,
    error: str = "",
) -> None:
    """内部辅助函数：_log。
    参数：session。
    """
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


def _public_library(row: VectorLibrary, permission: str = "owner") -> dict:
    """内部辅助函数：_public_library。
    参数：row / permission。
    """
    embedding = json.loads(row.embedding or "{}")
    if embedding.get("api_key"):
        embedding["api_key"] = SENTINEL
    return {
        "id": row.id,
        "name": row.name,
        "vector_type": row.vector_type,
        "description": row.description,
        "embedding": embedding,
        "config": json.loads(row.config or "{}"),
        "status": row.status,
        "origin": row.origin,
        "auto_parse": row.auto_parse,
        "parse_interval": row.parse_interval,
        "last_scan_at": row.last_scan_at.isoformat() if row.last_scan_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "permission": permission,
        "is_shared": permission != "owner",
    }


async def _accessible(
    session: AsyncSession, user_id: str, library_id: str, write: bool = False
) -> tuple[VectorLibrary, str]:
    """内部辅助函数：_accessible。
    参数：session / user_id / library_id / write。
    """
    row = await session.get(VectorLibrary, library_id)
    if row is None:
        raise ApiError("向量库不存在", code=404)
    if row.user_id == user_id:
        return row, "owner"
    share = (
        await session.execute(
            select(VectorLibraryShare).where(
                VectorLibraryShare.library_id == library_id,
                VectorLibraryShare.target_user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if share is None:
        raise ApiError("无权访问该向量库", code=403)
    if write and share.permission != "read_write":
        raise ApiError("该共享向量库只读", code=403)
    return row, share.permission


async def _accessible_ids(session: AsyncSession, user_id: str) -> list[str]:
    """内部辅助函数：_accessible_ids。
    参数：session / user_id。
    """
    own = (
        await session.execute(
            select(VectorLibrary.id).where(VectorLibrary.user_id == user_id)
        )
    ).scalars().all()
    shared = (
        await session.execute(
            select(VectorLibraryShare.library_id).where(
                VectorLibraryShare.target_user_id == user_id
            )
        )
    ).scalars().all()
    return list(dict.fromkeys([*own, *shared]))


async def async_libraries(params: dict) -> list[dict]:
    """列出本人及共享给自己的向量库。

        参数：session / user_id。
        """
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    own = (
        await session.execute(
            select(VectorLibrary)
            .where(VectorLibrary.user_id == user_id)
            .order_by(VectorLibrary.name)
        )
    ).scalars().all()
    shares = (
        await session.execute(
            select(VectorLibraryShare, VectorLibrary, User)
            .join(VectorLibrary, VectorLibrary.id == VectorLibraryShare.library_id)
            .join(User, User.id == VectorLibrary.user_id)
            .where(VectorLibraryShare.target_user_id == user_id)
            .order_by(VectorLibrary.name)
        )
    ).all()
    result = []
    for row in own:
        item = _public_library(row)
        docs = (
            await session.execute(
                select(VectorDocument).where(VectorDocument.library_id == row.id)
            )
        ).scalars().all()
        item["document_count"] = len(docs)
        item["chunk_count"] = sum(doc.chunk_count for doc in docs)
        item["share_count"] = int(
            (
                await session.execute(
                    select(func.count()).select_from(VectorLibraryShare).where(
                        VectorLibraryShare.library_id == row.id
                    )
                )
            ).scalar_one()
        )
        result.append(item)
    for share, row, owner in shares:
        item = _public_library(row, share.permission)
        item["owner_name"] = owner.nickname or owner.username
        docs = (
            await session.execute(
                select(VectorDocument).where(VectorDocument.library_id == row.id)
            )
        ).scalars().all()
        item["document_count"] = len(docs)
        item["chunk_count"] = sum(doc.chunk_count for doc in docs)
        result.append(item)
    return result


async def async_library_create(params: dict) -> dict:
    """创建向量库。

        参数：session / user_id / data。
        """
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
    row = VectorLibrary(
        user_id=user_id,
        name=name,
        vector_type=str(data.get("vector_type") or "sqlite"),
        description=str(data.get("description") or ""),
        embedding=json.dumps(data.get("embedding") or {}, ensure_ascii=False),
        config=json.dumps(data.get("config") or {}, ensure_ascii=False),
        auto_parse=bool(data.get("auto_parse")),
        parse_interval=max(60, min(int(data.get("parse_interval") or 300), 86400)),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _public_library(row)


async def async_library_update(params: dict) -> dict:
    """更新向量库配置。

        参数：session / user_id / library_id / data。
        """
    session: AsyncSession = params["session"]
    row, permission = await _accessible(
        session, params["user_id"], params["library_id"], write=True
    )
    if permission != "owner":
        raise ApiError("只有库主可以修改配置", code=403)
    data: dict = params["data"]
    if data.get("description") is not None:
        row.description = str(data["description"])
    if data.get("embedding") is not None:
        incoming = dict(data["embedding"])
        if incoming.get("api_key") == SENTINEL:
            current = json.loads(row.embedding or "{}")
            incoming["api_key"] = current.get("api_key", "")
        row.embedding = json.dumps(incoming, ensure_ascii=False)
    if data.get("config") is not None:
        row.config = json.dumps(data["config"], ensure_ascii=False)
    if data.get("status") in ("active", "inactive"):
        row.status = data["status"]
    if data.get("auto_parse") is not None:
        row.auto_parse = bool(data["auto_parse"])
    if data.get("parse_interval") is not None:
        row.parse_interval = max(60, min(int(data["parse_interval"]), 86400))
    await session.commit()
    await session.refresh(row)
    return _public_library(row)


async def async_library_delete(params: dict) -> None:
    """删除向量库及文档/切片。

        参数：session / library_id / user_id。
        """
    session: AsyncSession = params["session"]
    row = await session.get(VectorLibrary, params["library_id"])
    if row is None or row.user_id != params["user_id"]:
        raise ApiError("向量库不存在", code=404)
    try:
        await _call({"function": "delete_collection", "rag_config": _rag_config(row)})
    except Exception as exc:  # noqa: BLE001
        await _log(
            session, user_id=row.user_id, library_id=row.id,
            operation="delete_collection", status="failed", error=str(exc),
        )
    docs = (
        await session.execute(
            select(VectorDocument.id).where(VectorDocument.library_id == row.id)
        )
    ).scalars().all()
    if docs:
        await session.execute(delete(VectorChunk).where(VectorChunk.document_id.in_(docs)))
    await session.execute(delete(VectorDocument).where(VectorDocument.library_id == row.id))
    await session.execute(delete(VectorLibraryShare).where(VectorLibraryShare.library_id == row.id))
    shutil.rmtree(_library_dir(row.user_id, row.name), ignore_errors=True)
    await session.delete(row)
    await session.commit()


async def async_library_rebuild(params: dict) -> dict:
    """重建向量库索引。

        参数：session / library_id / user_id。
        """
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
    await session.execute(delete(VectorChunk).where(VectorChunk.library_id == row.id))
    await _log(
        session, user_id=row.user_id, library_id=row.id,
        operation="rebuild_index", status="success", details={"documents": len(docs)},
    )
    await session.commit()
    return {"library_id": row.id, "pending_documents": len(docs)}


async def async_library_test(params: dict) -> dict:
    """测试向量库连通性。

        参数：session / user_id / library_id。
        """
    session: AsyncSession = params["session"]
    row, _ = await _accessible(session, params["user_id"], params["library_id"])
    result = await _call({"function": "list", "rag_config": _rag_config(row)})
    return {"library_id": row.id, "collections": result.get("data") or []}


async def async_share_add(params: dict) -> dict:
    """共享向量库给指定用户。

        参数：permission / session / library_id / user_id / target_user_id。
        """
    session: AsyncSession = params["session"]
    library = await session.get(VectorLibrary, params["library_id"])
    if library is None or library.user_id != params["user_id"]:
        raise ApiError("向量库不存在", code=404)
    target = await session.get(User, params["target_user_id"])
    if target is None or not target.is_active:
        raise ApiError("目标用户不存在", code=404)
    if target.id == params["user_id"]:
        raise ApiError("不能共享给自己")
    permission = str(params.get("permission") or "read")
    if permission not in ("read", "read_write"):
        raise ApiError("权限只支持 read/read_write")
    row = (
        await session.execute(
            select(VectorLibraryShare).where(
                VectorLibraryShare.library_id == library.id,
                VectorLibraryShare.target_user_id == target.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = VectorLibraryShare(
            library_id=library.id,
            owner_user_id=params["user_id"],
            target_user_id=target.id,
            permission=permission,
        )
        session.add(row)
    else:
        row.permission = permission
    await session.commit()
    return {"library_id": library.id, "target_user_id": target.id, "permission": permission}


async def async_shares(params: dict) -> list[dict]:
    """列出向量库共享成员。

        参数：session / library_id / user_id。
        """
    session: AsyncSession = params["session"]
    library = await session.get(VectorLibrary, params["library_id"])
    if library is None or library.user_id != params["user_id"]:
        raise ApiError("向量库不存在", code=404)
    rows = (
        await session.execute(
            select(VectorLibraryShare, User)
            .join(User, User.id == VectorLibraryShare.target_user_id)
            .where(VectorLibraryShare.library_id == library.id)
        )
    ).all()
    return [
        {
            "id": share.id,
            "target_user_id": share.target_user_id,
            "target_name": user.nickname or user.username,
            "target_account": user.username,
            "permission": share.permission,
            "created_at": share.created_at.isoformat() if share.created_at else None,
        }
        for share, user in rows
    ]


async def async_share_remove(params: dict) -> None:
    """取消向量库共享。

        参数：session / library_id / user_id / target_user_id。
        """
    session: AsyncSession = params["session"]
    library = await session.get(VectorLibrary, params["library_id"])
    if library is None or library.user_id != params["user_id"]:
        raise ApiError("向量库不存在", code=404)
    await session.execute(
        delete(VectorLibraryShare).where(
            VectorLibraryShare.library_id == library.id,
            VectorLibraryShare.target_user_id == params["target_user_id"],
        )
    )
    await session.commit()


async def async_share_candidates(params: dict) -> list[dict]:
    """搜索可共享的用户。

        参数：q / session / user_id。
        """
    session: AsyncSession = params["session"]
    q = str(params.get("q") or "").strip()
    stmt = select(User).where(User.is_active.is_(True), User.id != params["user_id"])
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(User.username.ilike(like), User.nickname.ilike(like), User.email.ilike(like))
        )
    rows = (await session.execute(stmt.order_by(User.username).limit(20))).scalars().all()
    return [
        {"id": row.id, "username": row.username, "nickname": row.nickname}
        for row in rows
    ]


async def async_upload_document(params: dict) -> dict:
    """上传文档到向量库。

        参数：filename / session / user_id / library_id / content。
        """
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    library, permission = await _accessible(
        session, user_id, params["library_id"], write=True
    )
    if permission == "owner" and library.user_id != user_id:
        raise ApiError("无权写入", code=403)
    filename = Path(params.get("filename") or "file").name
    content: bytes = params["content"]
    if len(content) > 50 * 1024 * 1024:
        raise ApiError("文档不能超过 50MB")
    source_dir = _library_dir(library.user_id, library.name) / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    stored = source_dir / f"{uuid.uuid4().hex[:8]}_{filename}"
    stored.write_bytes(content)
    row = VectorDocument(
        user_id=library.user_id,
        library_id=library.id,
        filename=filename,
        source_path=str(stored),
        status="pending",
        filesize=len(content),
        parse_requested=False,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await _log(
        session, user_id=user_id, library_id=library.id, document_id=row.id,
        operation="upload", status="success", details={"filename": filename, "size": len(content)},
    )
    await session.commit()
    return _public_document(row)


def _public_document(row: VectorDocument) -> dict:
    """内部辅助函数：_public_document。
    参数：row。
    """
    return {
        "id": row.id,
        "library_id": row.library_id,
        "filename": row.filename,
        "status": row.status,
        "chunk_count": row.chunk_count,
        "filesize": row.filesize,
        "error_message": row.error_message,
        "parse_requested": row.parse_requested,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "parsed_at": row.parsed_at.isoformat() if row.parsed_at else None,
    }


async def async_documents(params: dict) -> dict:
    """列出可访问的文档。

        参数：library_id / status / session / user_id。
        """
    session: AsyncSession = params["session"]
    if params.get("library_id"):
        await _accessible(session, params["user_id"], params["library_id"])
        ids = [params["library_id"]]
    else:
        ids = await _accessible_ids(session, params["user_id"])
    if not ids:
        return {"documents": [], "total": 0}
    stmt = select(VectorDocument).where(VectorDocument.library_id.in_(ids))
    if params.get("status"):
        stmt = stmt.where(VectorDocument.status == params["status"])
    rows = (
        await session.execute(stmt.order_by(VectorDocument.created_at.desc()))
    ).scalars().all()
    return {"documents": [_public_document(row) for row in rows], "total": len(rows)}


async def _parse_document(session: AsyncSession, doc: VectorDocument) -> VectorDocument:
    """内部辅助函数：_parse_document。
    参数：session / doc。
    """
    library = await session.get(VectorLibrary, doc.library_id)
    if library is None:
        raise ApiError("向量库不存在", code=404)
    doc.status = "parsing"
    await session.commit()
    try:
        embedding = await _embedding(session, library)
        config = json.loads(library.config or "{}")
        file_config = {
            "file_path": doc.source_path,
            "file_name": Path(doc.source_path).name,
        }
        chunker = {
            "chunk_size": int(config.get("chunk_size") or 256),
            "overlap": int(config.get("overlap") or 0),
        }
        from scope.rag.common import async_get_chunks, get_chunk_text

        parsed = await async_get_chunks(
            {"file_config": file_config, "file_chunker": chunker}
        )
        if parsed.get("code") != 200:
            raise ApiError(parsed.get("message") or "文档切片失败")
        chunk_texts = [
            get_chunk_text(chunk) for chunk in (parsed.get("data") or [])
        ]
        result = await _call(
            {
                "function": "write",
                "rag_config": _rag_config(library),
                "file_config": file_config,
                "file_chunker": chunker,
                "embedding": embedding,
            }
        )
        chunks = result.get("data") or []
        doc.status = "parsed"
        doc.chunk_count = len(chunks) if isinstance(chunks, list) else len(chunk_texts)
        doc.error_message = ""
        doc.parsed_at = datetime.now(timezone.utc)
        await session.execute(delete(VectorChunk).where(VectorChunk.document_id == doc.id))
        for index, text in enumerate(chunk_texts):
            session.add(
                VectorChunk(
                    document_id=doc.id,
                    library_id=doc.library_id,
                    chunk_index=index,
                    text=text,
                )
            )
        await _log(
            session, user_id=doc.user_id, library_id=library.id, document_id=doc.id,
            operation="parse", status="success", details={"chunks": doc.chunk_count},
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
    return doc


async def async_parse_document(params: dict) -> dict:
    """加入后台解析队列，不在请求线程里执行文档解析。"""
    session: AsyncSession = params["session"]
    doc = await session.get(VectorDocument, params["document_id"])
    if doc is None:
        raise ApiError("文档不存在", code=404)
    await _accessible(session, params["user_id"], doc.library_id, write=True)
    if doc.status == "parsing":
        return {**_public_document(doc), "queued": True, "already_running": True}
    doc.parse_requested = True
    if doc.status == "failed":
        doc.error_message = ""
    await session.commit()
    await session.refresh(doc)
    return {**_public_document(doc), "queued": True}


async def async_parse_pending(params: dict) -> dict:
    """把待解析/失败文档加入解析队列。

        参数：session / user_id / library_id。
        """
    session: AsyncSession = params["session"]
    library, _ = await _accessible(
        session, params["user_id"], params["library_id"], write=True
    )
    docs = (
        await session.execute(
            select(VectorDocument).where(
                VectorDocument.library_id == library.id,
                VectorDocument.status.in_(("pending", "failed")),
            )
        )
    ).scalars().all()
    for doc in docs:
        doc.parse_requested = True
        if doc.status == "failed":
            doc.error_message = ""
    await session.commit()
    return {"library_id": library.id, "total": len(docs), "queued": len(docs)}


async def async_parse_config(params: dict) -> dict:
    """读取知识库解析并发配置。

        参数：session。
        """
    session: AsyncSession = params["session"]
    concurrency = int(
        await async_get_config(
            {"session": session, "key": "knowledge.parse_concurrency", "default": 2}
        ) or 2
    )
    mode = str(
        await async_get_config(
            {"session": session, "key": "knowledge.parse_queue_mode", "default": "fifo"}
        ) or "fifo"
    )
    interval = int(
        await async_get_config(
            {"session": session, "key": "knowledge.worker_interval", "default": 5}
        ) or 5
    )
    return {
        "parse_concurrency": max(1, min(concurrency, 8)),
        "queue_mode": mode if mode in ("fifo", "lifo") else "fifo",
        "worker_interval": max(2, min(interval, 60)),
    }


async def async_set_parse_config(params: dict) -> dict:
    """保存知识库解析并发配置。

        参数：session / data / operator_id。
        """
    from app.services.config.service import async_update_config

    session: AsyncSession = params["session"]
    data: dict = params["data"]
    concurrency = max(1, min(int(data.get("parse_concurrency") or 2), 8))
    mode = str(data.get("queue_mode") or "fifo")
    if mode not in ("fifo", "lifo"):
        raise ApiError("排队顺序只支持 fifo/lifo")
    interval = max(2, min(int(data.get("worker_interval") or 5), 60))
    for key, value in (
        ("knowledge.parse_concurrency", concurrency),
        ("knowledge.parse_queue_mode", mode),
        ("knowledge.worker_interval", interval),
    ):
        await async_update_config(
            {
                "session": session,
                "key": key,
                "value": value,
                "operator_id": params["operator_id"],
            }
        )
    return await async_parse_config({"session": session})


async def async_claim_parse_documents(params: dict) -> list[dict]:
    """原子认领待解析文档，返回可供 worker 处理的最小快照。"""
    session: AsyncSession = params["session"]
    limit = max(1, min(int(params.get("limit") or 2), 16))
    order = VectorDocument.created_at.asc() if params.get("queue_mode") != "lifo" \
        else VectorDocument.created_at.desc()
    docs = (
        await session.execute(
            select(VectorDocument)
            .where(
                VectorDocument.parse_requested.is_(True),
                VectorDocument.status.in_(("pending", "failed")),
            )
            .order_by(order)
            .limit(limit)
        )
    ).scalars().all()
    claimed = []
    for doc in docs:
        result = await session.execute(
            update(VectorDocument)
            .where(
                VectorDocument.id == doc.id,
                VectorDocument.parse_requested.is_(True),
                VectorDocument.status.in_(("pending", "failed")),
            )
            .values(status="parsing", error_message="")
        )
        if result.rowcount == 1:
            claimed.append({"document_id": doc.id})
    await session.commit()
    return claimed


async def async_run_claimed(params: dict) -> dict | None:
    """执行一个已认领的文档解析任务。

        参数：session / document_id。
        """
    session: AsyncSession = params["session"]
    doc = await session.get(VectorDocument, params["document_id"])
    if doc is None:
        return None
    doc = await _parse_document(session, doc)
    doc.parse_requested = False
    await session.commit()
    return _public_document(doc)


async def async_delete_document(params: dict) -> None:
    """删除文档、切片与源文件。

        参数：session / document_id / user_id。
        """
    session: AsyncSession = params["session"]
    doc = await session.get(VectorDocument, params["document_id"])
    if doc is None:
        raise ApiError("文档不存在", code=404)
    await _accessible(session, params["user_id"], doc.library_id, write=True)
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
    await session.execute(delete(VectorChunk).where(VectorChunk.document_id == doc.id))
    await _log(
        session, user_id=params["user_id"], library_id=doc.library_id,
        document_id=doc.id, operation="delete", status="success",
    )
    await session.delete(doc)
    await session.commit()


async def async_chunks(params: dict) -> dict:
    """读取文档切片。

        参数：session / document_id / user_id。
        """
    session: AsyncSession = params["session"]
    doc = await session.get(VectorDocument, params["document_id"])
    if doc is None:
        raise ApiError("文档不存在", code=404)
    await _accessible(session, params["user_id"], doc.library_id)
    rows = (
        await session.execute(
            select(VectorChunk)
            .where(VectorChunk.document_id == doc.id)
            .order_by(VectorChunk.chunk_index)
        )
    ).scalars().all()
    return {
        "document": _public_document(doc),
        "chunks": [
            {"index": row.chunk_index, "text": row.text, "id": row.id} for row in rows
        ],
    }


async def async_document_file(params: dict) -> tuple[Path, str]:
    """返回文档源文件路径与文件名。

        参数：session / document_id / user_id。
        """
    session: AsyncSession = params["session"]
    doc = await session.get(VectorDocument, params["document_id"])
    if doc is None:
        raise ApiError("文档不存在", code=404)
    await _accessible(session, params["user_id"], doc.library_id)
    path = Path(doc.source_path)
    if not path.is_file():
        raise ApiError("源文件不存在", code=404)
    return path, doc.filename


async def async_search(params: dict) -> dict:
    """跨可访问向量库检索。

        参数：library_ids / top_k / score_threshold / session / user_id / query。
        """
    session: AsyncSession = params["session"]
    user_id = params["user_id"]
    libraries = []
    if params.get("library_ids"):
        for library_id in params["library_ids"]:
            try:
                row, _ = await _accessible(session, user_id, library_id)
                libraries.append(row)
            except ApiError:
                continue
    else:
        ids = await _accessible_ids(session, user_id)
        if ids:
            libraries = list(
                (
                    await session.execute(
                        select(VectorLibrary).where(
                            VectorLibrary.id.in_(ids), VectorLibrary.status == "active"
                        )
                    )
                ).scalars().all()
            )
    results = []
    errors = []
    for library in libraries:
        try:
            embedding = await _embedding(session, library)
            result = await _call(
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
            data = result.get("data") if isinstance(result, dict) else result
            items = data if isinstance(data, list) else (data or {}).get("results") or []
            for item in items:
                if isinstance(item, dict):
                    item["library_name"] = library.name
                    item["library_id"] = library.id
                    item["score"] = float(item.get("score") or 0)
            results.extend(items)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {"library_id": library.id, "library_name": library.name, "error": str(exc)}
            )
    results.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    await _log(
        session, user_id=user_id, operation="search", status="success",
        details={
            "query": params["query"], "hits": len(results),
            "libraries": [lib.name for lib in libraries],
        },
    )
    await session.commit()
    return {
        "results": results[: int(params.get("top_k") or 5) * max(1, len(libraries))],
        "errors": errors,
        "searched_libraries": [lib.name for lib in libraries],
    }


async def async_logs(params: dict) -> dict:
    """列出知识库操作日志。

        参数：library_id / session / user_id。
        """
    session: AsyncSession = params["session"]
    stmt = select(VectorLog).where(VectorLog.user_id == params["user_id"])
    if params.get("library_id"):
        await _accessible(session, params["user_id"], params["library_id"])
        stmt = stmt.where(VectorLog.library_id == params["library_id"])
    rows = (
        await session.execute(stmt.order_by(VectorLog.created_at.desc()).limit(200))
    ).scalars().all()
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


async def async_auto_parse_once(params: dict) -> dict:
    """扫描开启自动解析且到期的库，解析其 pending/failed 文档。"""
    session: AsyncSession = params["session"]
    now = datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(VectorLibrary).where(VectorLibrary.auto_parse.is_(True))
        )
    ).scalars().all()
    processed = 0
    for library in rows:
        last = library.last_scan_at
        if last is not None:
            elapsed = (now - last).total_seconds()
            if elapsed < max(60, library.parse_interval):
                continue
        docs = (
            await session.execute(
                select(VectorDocument).where(
                    VectorDocument.library_id == library.id,
                    VectorDocument.status.in_(("pending", "failed")),
                )
            )
        ).scalars().all()
        for doc in docs:
            doc.parse_requested = True
            processed += 1
        library.last_scan_at = now
        await session.commit()
    return {"processed": processed, "libraries": len(rows)}
