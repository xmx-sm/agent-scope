"""用户 Skills 管理。"""

import shutil
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import User, UserSkill
from app.services.agent.runtime.scope_bridge import ROOT

SKILL_ROOT = ROOT / "backend" / "uploads" / "agents"


def _skill_root(user_id: str) -> Path:
    """内部辅助函数：_skill_root。
    参数：user_id。
    """
    path = SKILL_ROOT / f"user_{user_id}" / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def async_list(params: dict) -> list[dict]:
    """列出用户 Skills。

        参数：session / user。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserSkill).where(UserSkill.user_id == user.id).order_by(UserSkill.name)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "directory": row.directory,
            "is_active": row.is_active,
        }
        for row in rows
    ]


def _safe_extract(zip_path: Path, target: Path) -> None:
    """内部辅助函数：_safe_extract。
    参数：zip_path / target。
    """
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            if name.startswith("/") or ".." in Path(name).parts:
                raise ApiError("压缩包包含非法路径")
            archive.extract(member, target)


async def async_upload_zip(params: dict) -> dict:
    """上传并安全解压 Skills ZIP。

        参数：name / session / user / filename / content。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    filename: str = params["filename"]
    content: bytes = params["content"]
    name = str(params.get("name") or Path(filename).stem).strip()
    if not name:
        raise ApiError("技能名不能为空")
    if len(content) > 20 * 1024 * 1024:
        raise ApiError("技能包不能超过 20MB")

    root = _skill_root(user.id)
    target = root / name
    if target.exists():
        shutil.rmtree(target)
    tmp = root / f".upload_{name}.zip"
    tmp.write_bytes(content)
    try:
        _safe_extract(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)

    # 支持 SKILL.md 在根目录或单层子目录
    if not (target / "SKILL.md").is_file():
        children = [p for p in target.iterdir() if p.is_dir()]
        if len(children) == 1 and (children[0] / "SKILL.md").is_file():
            nested = children[0]
            for item in nested.iterdir():
                shutil.move(str(item), target / item.name)
            nested.rmdir()

    skill_md = target / "SKILL.md"
    description = ""
    if skill_md.is_file():
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.lower().startswith("description:"):
                description = line.split(":", 1)[1].strip()[:500]
                break
    row = (
        await session.execute(
            select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.name == name)
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserSkill(user_id=user.id, name=name, directory=str(target))
        session.add(row)
    row.description = description
    row.directory = str(target)
    row.is_active = True
    await session.commit()
    await session.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "is_active": row.is_active,
    }


async def async_delete(params: dict) -> None:
    """删除 Skills。

        参数：session / user / skill_id。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    row = await session.get(UserSkill, params["skill_id"])
    if row is None or row.user_id != user.id:
        raise ApiError("技能不存在", code=404)
    target = Path(row.directory)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    await session.delete(row)
    await session.commit()


async def async_toggle(params: dict) -> dict:
    """启停 Skills。

        参数：is_active / session / user / skill_id。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    row = await session.get(UserSkill, params["skill_id"])
    if row is None or row.user_id != user.id:
        raise ApiError("技能不存在", code=404)
    row.is_active = bool(params.get("is_active"))
    await session.commit()
    return {"id": row.id, "is_active": row.is_active}


async def async_active_dirs(params: dict) -> list[str]:
    """返回启用中的 Skills 目录。

        参数：session / user。
        """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserSkill).where(
                UserSkill.user_id == user.id, UserSkill.is_active.is_(True)
            )
        )
    ).scalars().all()
    return [row.directory for row in rows if Path(row.directory).is_dir()]
