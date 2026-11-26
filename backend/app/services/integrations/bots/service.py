"""机器人管理业务。"""

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import User, UserBot
from app.utils.secret_box import decrypt_secret, encrypt_secret


def _public(row: UserBot, secret: str | None = None) -> dict:
    """返回机器人信息，密钥只在创建或轮换时返回。"""
    data = {
        "id": row.id,
        "name": row.name,
        "platform": row.platform,
        "enabled": row.enabled,
        "tools_enabled": row.tools_enabled,
        "timeout_seconds": row.timeout_seconds,
        "webhook_path": f"/api/public/bots/{row.id}/webhook",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if secret is not None:
        data["secret"] = secret
    return data


async def async_list(params: dict) -> list[dict]:
    """列出当前用户的机器人。参数：session / user。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    rows = (
        await session.execute(
            select(UserBot).where(UserBot.user_id == user.id).order_by(UserBot.created_at.desc())
        )
    ).scalars().all()
    return [_public(row) for row in rows]


async def async_get_owned(params: dict) -> UserBot:
    """读取当前用户拥有的机器人。参数：session / user / bot_id。"""
    session: AsyncSession = params["session"]
    row = await session.get(UserBot, params["bot_id"])
    if row is None or row.user_id != params["user"].id:
        raise ApiError("机器人不存在", code=404)
    return row


async def async_get(params: dict) -> dict:
    """返回当前用户的机器人详情。参数：session / user / bot_id。"""
    row = await async_get_owned(params)
    return _public(row)


async def async_create(params: dict) -> dict:
    """创建机器人并生成接入密钥。参数：session / user / data。"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    data = params["data"]
    secret = secrets.token_urlsafe(32)
    row = UserBot(
        user_id=user.id,
        name=data["name"].strip(),
        platform=data.get("platform") or "webhook",
        credential_ciphertext=encrypt_secret(secret),
        config_json="{}",
        enabled=True,
        tools_enabled=bool(data.get("tools_enabled", False)),
        timeout_seconds=int(data.get("timeout_seconds") or 120),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _public(row, secret)


async def async_update(params: dict) -> dict:
    """更新机器人设置。参数：session / user / bot_id / data。"""
    session: AsyncSession = params["session"]
    row = await async_get_owned(params)
    data = params["data"]
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "enabled" in data and data["enabled"] is not None:
        row.enabled = bool(data["enabled"])
    if "tools_enabled" in data and data["tools_enabled"] is not None:
        row.tools_enabled = bool(data["tools_enabled"])
    if "timeout_seconds" in data and data["timeout_seconds"] is not None:
        row.timeout_seconds = int(data["timeout_seconds"])
    await session.commit()
    await session.refresh(row)
    return _public(row)


async def async_delete(params: dict) -> None:
    """删除机器人。参数：session / user / bot_id。"""
    session: AsyncSession = params["session"]
    row = await async_get_owned(params)
    await session.delete(row)
    await session.commit()


async def async_rotate_secret(params: dict) -> dict:
    """轮换机器人接入密钥。参数：session / user / bot_id。"""
    session: AsyncSession = params["session"]
    row = await async_get_owned(params)
    secret = secrets.token_urlsafe(32)
    row.credential_ciphertext = encrypt_secret(secret)
    await session.commit()
    await session.refresh(row)
    return _public(row, secret)


async def async_decrypt_credential(params: dict) -> str:
    """读取机器人明文凭据供验签使用。参数：bot。"""
    return decrypt_secret(params["bot"].credential_ciphertext)
