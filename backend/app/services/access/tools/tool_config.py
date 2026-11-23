"""用户工具连接配置：邮箱 / 数据库。"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import User, UserToolConfig
from app.services.config.service import async_get_config
from app.utils.mask import SENTINEL, mask_secret

CATEGORIES = ("email", "db", "embedding")
SECRET_FIELDS = {"email": ("password",), "db": ("password",), "embedding": ("api_key",)}


def _mask(category: str, config: dict) -> dict:
    """内部辅助函数：_mask。
    参数：category / config。
    """
    out = dict(config)
    for key in SECRET_FIELDS.get(category, ()):
        out[key] = mask_secret(out.get(key))
    return out


async def _system_config(session: AsyncSession, category: str) -> dict[str, Any]:
    """内部辅助函数：_system_config。
    参数：session / category。
    """
    async def get(key: str, default: Any = ""):
        """读取系统配置。"""
        return await async_get_config({"session": session, "key": key, "default": default})

    if category == "email":
        return {
            "smtp_host": await get("mail.smtp.host", ""),
            "smtp_port": await get("mail.smtp.port", 465),
            "host_user": await get("mail.smtp.user", ""),
            "password": await get("mail.smtp.password", ""),
            "imap_host": await get("mail.imap.host", ""),
            "imap_port": await get("mail.imap.port", 993),
            "from_address": await get("mail.from_address", ""),
            "from_name": await get("mail.from_name", "Agent Scope"),
            "use_tls": await get("mail.use_tls", True),
        }
    if category == "embedding":
        return {
            "provider": await get("ai.embedding.provider", ""),
            "base_url": await get("ai.embedding.base_url", ""),
            "api_key": await get("ai.embedding.api_key", ""),
            "model": await get("ai.embedding.model", ""),
            "dimensions": await get("ai.embedding.dimensions", 0),
        }
    return {
        "db_type": await get("db.default_type", ""),
        "host": await get("db.default_host", ""),
        "port": await get("db.default_port", 0),
        "user": await get("db.default_user", ""),
        "password": await get("db.default_password", ""),
        "database": await get("db.default_database", ""),
        "path": await get("db.default_path", ""),
        "dir": await get("db.default_dir", ""),
        "allow_write": await get("db.allow_write", False),
    }


async def _get_row(session: AsyncSession, user_id: str, category: str):
    """内部辅助函数：_get_row。
    参数：session / user_id / category。
    """
    return (
        await session.execute(
            select(UserToolConfig).where(
                UserToolConfig.user_id == user_id,
                UserToolConfig.category == category,
            )
        )
    ).scalar_one_or_none()


async def async_effective(params: dict) -> dict[str, Any]:
    """合并系统默认与用户工具连接配置

    参数：session / user_id / category
    """
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    category: str = params["category"]
    system = await _system_config(session, category)
    record = await _get_row(session, user_id, category)
    if record is None or record.use_default:
        return system
    try:
        user_cfg = json.loads(record.config_data or "{}")
    except (ValueError, TypeError):
        user_cfg = {}
    merged = dict(system)
    merged.update(user_cfg)
    return merged


async def async_view(params: dict) -> dict[str, Any]:
    """查看用户工具连接配置

    参数：session / user_id / category
    """
    session: AsyncSession = params["session"]
    user_id: str = params["user_id"]
    category: str = params["category"]
    if category not in CATEGORIES:
        raise ApiError("未知工具配置类别")
    system = await _system_config(session, category)
    record = await _get_row(session, user_id, category)
    use_default = bool(record.use_default) if record else True
    try:
        user_cfg = json.loads(record.config_data or "{}") if record else {}
    except (ValueError, TypeError):
        user_cfg = {}
    effective = dict(system)
    if not use_default:
        effective.update(user_cfg)
    return {
        "category": category,
        "use_default": use_default,
        "system": _mask(category, system),
        "user": _mask(category, user_cfg),
        "effective": _mask(category, effective),
    }


async def async_save(params: dict) -> dict[str, Any]:
    """保存用户工具连接配置

    参数：session / user / category / data
    """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    category: str = params["category"]
    data: dict = params["data"]
    if category not in CATEGORIES:
        raise ApiError("未知工具配置类别")

    record = await _get_row(session, user.id, category)
    if record is None:
        record = UserToolConfig(user_id=user.id, category=category, use_default=True,
                                config_data="{}")
        session.add(record)

    use_default = bool(data.get("use_default", True))
    record.use_default = use_default
    if not use_default:
        system = await _system_config(session, category)
        current = {}
        try:
            current = json.loads(record.config_data or "{}")
        except (ValueError, TypeError):
            current = {}
        config = dict(data.get("config") or {})
        for field in SECRET_FIELDS.get(category, ()):
            if config.get(field) == SENTINEL:
                config[field] = current.get(field) or system.get(field) or ""
        if category == "email":
            if not str(config.get("smtp_host") or "").strip():
                raise ApiError("自定义邮箱配置必须填写 SMTP 服务器")
            if not str(config.get("host_user") or "").strip():
                raise ApiError("自定义邮箱配置必须填写邮箱账号")
        elif category == "embedding":
            if not str(config.get("provider") or "").strip():
                raise ApiError("自定义 Embedding 配置必须填写服务商")
            if not str(config.get("model") or "").strip():
                raise ApiError("自定义 Embedding 配置必须填写模型")
        else:
            db_type = str(config.get("db_type") or "").strip()
            if db_type not in ("postgresql", "mysql", "mongodb", "sqlite"):
                raise ApiError("数据库类型只支持 postgresql/mysql/mongodb/sqlite")
            if db_type == "sqlite":
                if not (config.get("path") or config.get("dir")):
                    raise ApiError("SQLite 需要配置 path 或 dir")
            elif not str(config.get("host") or "").strip():
                raise ApiError("自定义数据库配置必须填写主机")
        record.config_data = json.dumps(config, ensure_ascii=False)
    await session.commit()
    return await async_view(
        {"session": session, "user_id": user.id, "category": category}
    )


async def async_reset(params: dict) -> dict[str, Any]:
    """恢复工具连接系统默认

    参数：session / user / category
    """
    session: AsyncSession = params["session"]
    user: User = params["user"]
    category: str = params["category"]
    record = await _get_row(session, user.id, category)
    if record is not None:
        record.use_default = True
        await session.commit()
    return await async_view(
        {"session": session, "user_id": user.id, "category": category}
    )


async def async_test_email(params: dict) -> dict:
    """测试邮箱连接

    参数：session / user_id
    """
    import aiosmtplib

    session: AsyncSession = params["session"]
    cfg = await async_effective(
        {"session": session, "user_id": params["user_id"], "category": "email"}
    )
    host = str(cfg.get("smtp_host") or "").strip()
    if not host:
        raise ApiError("请先配置 SMTP 服务器")
    port = int(cfg.get("smtp_port") or 465)
    user = str(cfg.get("host_user") or "").strip()
    password = str(cfg.get("password") or "")
    use_tls = bool(cfg.get("use_tls", True))
    try:
        smtp = aiosmtplib.SMTP(
            hostname=host,
            port=port,
            timeout=10,
            use_tls=(use_tls and port == 465),
            start_tls=(use_tls and port != 465),
        )
        await smtp.connect()
        if user:
            await smtp.login(user, password)
        await smtp.quit()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(f"邮箱连接失败：{exc}")
    return {"connected": True, "host": host, "port": port}


async def async_test_db(params: dict) -> dict:
    """测试数据库连接

    参数：session / user_id
    """
    from app.services.agent.runtime.scope_bridge import SCOPE_DIR  # noqa: F401
    from scope.tools.db.main_db import async_db_tools

    session: AsyncSession = params["session"]
    cfg = await async_effective(
        {"session": session, "user_id": params["user_id"], "category": "db"}
    )
    db_config = {
        key: cfg.get(key)
        for key in ("db_type", "host", "port", "user", "password", "database", "path", "dir")
        if cfg.get(key) not in (None, "")
    }
    if not db_config.get("db_type"):
        raise ApiError("请先配置数据库类型")
    result = await async_db_tools(
        {"function": "list_databases", "db_config": db_config}
    )
    if result.get("code") != 200:
        raise ApiError(result.get("message") or "数据库连接失败")
    return {"connected": True, "databases": result.get("data")}
