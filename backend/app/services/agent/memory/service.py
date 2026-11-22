"""用户长期记忆文件管理。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import User, UserAgentConfig
from app.services.agent.config.user_config import async_effective
from app.services.agent.runtime.scope_bridge import ROOT

MEMORY_ROOT = ROOT / "backend" / "uploads" / "agents"
MAX_READ_BYTES = 1024 * 1024


def _root(user_id: str) -> Path:
    """确保并返回用户记忆目录。参数：user_id。"""
    path = MEMORY_ROOT / f"user_{user_id}" / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_path(user_id: str, name: str) -> Path:
    """校验记忆文件名并返回安全路径。参数：user_id / name。"""
    root = _root(user_id)
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ApiError("非法记忆文件路径", code=400) from exc
    if not candidate.is_file():
        raise ApiError("记忆文件不存在", code=404)
    return candidate


def _files(user_id: str) -> list[Path]:
    """列出用户记忆目录下的文件。参数：user_id。"""
    root = _root(user_id)
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


async def async_status(params: dict) -> dict:
    """查看长期记忆状态与占用。参数：session / user。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    effective = await async_effective({"session": session, "user": user})
    row = await session.get(UserAgentConfig, user.id)
    files = _files(user.id)
    total = sum(path.stat().st_size for path in files)
    last_modified = max((path.stat().st_mtime for path in files), default=None)
    return {
        "enabled": bool(effective.get("memory_enabled")),
        "configured": bool(row.memory_configured) if row else False,
        "source": "user" if row is not None and row.memory_configured else "system",
        "path": str(_root(user.id)),
        "file_count": len(files),
        "bytes": total,
        "last_modified": (
            datetime.fromtimestamp(last_modified, tz=timezone.utc).isoformat()
            if last_modified
            else None
        ),
    }


async def async_files(params: dict) -> list[dict]:
    """列出记忆文件。参数：user。"""
    user: User = params["user"]
    root = _root(user.id)
    result = []
    for path in _files(user.id):
        result.append(
            {
                "name": str(path.relative_to(root)),
                "size": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return result


async def async_read(params: dict) -> dict:
    """读取记忆文件内容。参数：user / name。"""
    user: User = params["user"]
    path = _safe_path(user.id, params["name"])
    if path.stat().st_size > MAX_READ_BYTES:
        raise ApiError("记忆文件过大，不能在线预览")
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ApiError(f"读取记忆失败：{exc}") from exc
    return {"name": params["name"], "content": content, "size": path.stat().st_size}


async def async_delete_file(params: dict) -> None:
    """删除单个记忆文件。参数：user / name。"""
    user: User = params["user"]
    path = _safe_path(user.id, params["name"])
    path.unlink(missing_ok=True)


async def async_clear(params: dict) -> dict:
    """清空用户全部长期记忆。参数：user。"""
    import shutil

    user: User = params["user"]
    root = _root(user.id)
    removed = 0
    for child in list(root.iterdir()):
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
        removed += 1
    return {"removed": removed}


async def async_set_enabled(params: dict) -> dict:
    """设置长期记忆开关。参数：session / user / enabled。"""
    from app.services.agent.config.user_config import async_set_memory

    view = await async_set_memory(
        {
            "session": params["session"],
            "user": params["user"],
            "enabled": bool(params.get("enabled")),
        }
    )
    status = await async_status({"session": params["session"], "user": params["user"]})
    status["effective"] = view["effective"]
    return status
