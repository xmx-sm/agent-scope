"""对话附件：上传、读取、模型输入转换。"""

import base64
import mimetypes
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import AgentAttachment, AgentMessage, User
from app.services.agent.scope_bridge import ROOT

ATTACHMENT_ROOT = ROOT / "backend" / "uploads" / "agents"
MAX_SIZE = 20 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
TEXT_TYPES = {
    "text/plain", "text/markdown", "application/json", "text/csv", "text/html",
    "application/xml", "text/xml",
}


async def async_upload(params: dict) -> dict:
    """参数：session / user / file"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    file: UploadFile = params["file"]
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise ApiError("附件不能超过 20MB")
    filename = Path(file.filename or "file").name
    ext = Path(filename).suffix[:20]
    mime_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    target_dir = ATTACHMENT_ROOT / f"user_{user.id}" / "attachments"
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = target_dir / f"{uuid.uuid4().hex}{ext}"
    stored.write_bytes(content)
    row = AgentAttachment(
        user_id=user.id,
        filename=filename,
        path=str(stored),
        mime_type=mime_type,
        size=len(content),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": row.id,
        "filename": row.filename,
        "mime_type": row.mime_type,
        "size": row.size,
        "is_image": row.mime_type in IMAGE_TYPES,
        "is_text": row.mime_type in TEXT_TYPES,
    }


async def async_get_owned(params: dict) -> AgentAttachment:
    session: AsyncSession = params["session"]
    row = await session.get(AgentAttachment, params["attachment_id"])
    if row is None or row.user_id != params["user_id"]:
        raise ApiError("附件不存在", code=404)
    return row


async def async_load_for_model(params: dict) -> tuple[list[dict], str, list[dict]]:
    """参数：session / user_id / ids
    返回 (消息附件元数据, 追加文本, 图片 DataBlock 参数)。
    """
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    ids: list[str] = params.get("ids") or []
    meta: list[dict] = []
    text_parts: list[str] = []
    images: list[dict] = []
    for attachment_id in ids:
        row = await session.get(AgentAttachment, attachment_id)
        if row is None or row.user_id != user_id:
            continue
        item = {
            "id": row.id,
            "filename": row.filename,
            "mime_type": row.mime_type,
            "size": row.size,
        }
        meta.append(item)
        if row.mime_type in IMAGE_TYPES:
            data = base64.b64encode(Path(row.path).read_bytes()).decode()
            images.append({"data": data, "media_type": row.mime_type, "name": row.filename})
        elif row.mime_type in TEXT_TYPES:
            try:
                text = Path(row.path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            text_parts.append(f"[附件 {row.filename}]\n{text[:20000]}")
        else:
            text_parts.append(f"[附件 {row.filename}，类型 {row.mime_type}，暂未解析内容]")
    return meta, "\n\n".join(text_parts), images


async def async_list_message_attachments(session: AsyncSession, message: AgentMessage) -> list[dict]:
    import json

    try:
        data = json.loads(message.attachments or "[]")
    except (ValueError, TypeError):
        data = []
    return data if isinstance(data, list) else []
