"""数据库访问默认策略：库/表白名单、黑名单与模型连接限制。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config.service import async_get_config


def _split(value: Any) -> list[str]:
    if not value:
        return []
    return [
        item.strip().lower()
        for item in str(value).replace("\n", ",").split(",")
        if item.strip()
    ]


async def async_get_db_policy(params: dict) -> dict[str, Any]:
    """参数：session"""
    session: AsyncSession = params["session"]

    async def get(key: str, default: Any):
        return await async_get_config({"session": session, "key": key, "default": default})

    return {
        "allow_all_tables": bool(await get("db.allow_all_tables", False)),
        "allowed_databases": _split(await get("db.allowed_databases", "")),
        "allowed_tables": _split(await get("db.allowed_tables", "")),
        "denied_databases": _split(await get("db.denied_databases", "")),
        "denied_tables": _split(await get("db.denied_tables", "")),
        "allow_write": bool(await get("db.allow_write", False)),
        "allow_model_db_config": bool(await get("security.allow_model_db_config", False)),
    }


def _matches(table_ref: str, db_name: str, table: str) -> bool:
    ref = table_ref.lower()
    return ref in (table.lower(), f"{db_name.lower()}.{table.lower()}")


def is_database_allowed(policy: dict, db_name: str) -> bool:
    db = (db_name or "").lower()
    if db in policy["denied_databases"]:
        return False
    allowed = policy["allowed_databases"]
    return not allowed or db in allowed


def is_table_allowed(policy: dict, db_name: str, table: str) -> bool:
    if not is_database_allowed(policy, db_name):
        return False
    if any(_matches(item, db_name, table) for item in policy["denied_tables"]):
        return False
    if policy["allow_all_tables"]:
        return True
    return any(_matches(item, db_name, table) for item in policy["allowed_tables"])


def apply_db_policy(policy: dict, db_config: dict) -> dict:
    """把默认策略压到 db_config 上；模型自传连接默认被剥离。"""
    config = dict(db_config or {})
    if not policy["allow_model_db_config"]:
        for key in ("host", "port", "user", "password", "path", "dir"):
            config.pop(key, None)
    config["allow_write"] = bool(policy["allow_write"] and config.get("allow_write", True))
    config["allowed_databases"] = policy["allowed_databases"]
    config["allowed_tables"] = policy["allowed_tables"]
    config["denied_databases"] = policy["denied_databases"]
    config["denied_tables"] = policy["denied_tables"]
    return config
