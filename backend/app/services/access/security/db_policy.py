"""数据库访问默认策略：库/表白名单、黑名单与模型连接限制。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config.service import async_get_config


def _split(value: Any) -> list[str]:
    """内部辅助函数：_split。

    内部辅助：拆分逗号/换行分隔的配置。
    """
    if not value:
        return []
    return [
        item.strip().lower()
        for item in str(value).replace("\n", ",").split(",")
        if item.strip()
    ]


async def async_get_db_policy(params: dict) -> dict[str, Any]:
    """读取数据库安全策略

    参数：session
    """
    session: AsyncSession = params["session"]

    async def get(key: str, default: Any):
        """读取系统配置。"""
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
    """内部辅助函数：_matches。
    参数：table_ref / db_name / table。
    """
    ref = table_ref.lower()
    return ref in (table.lower(), f"{db_name.lower()}.{table.lower()}")


def is_database_allowed(params: dict) -> bool:
    """判断数据库是否被默认策略允许。参数：policy / db_name。"""
    policy = params["policy"]
    db = (params.get("db_name") or "").lower()
    if db in policy["denied_databases"]:
        return False
    allowed = policy["allowed_databases"]
    return not allowed or db in allowed


def is_table_allowed(params: dict) -> bool:
    """判断库表是否被默认策略允许。参数：policy / db_name / table。"""
    policy = params["policy"]
    db_name = params.get("db_name") or ""
    table = params.get("table") or ""
    if not is_database_allowed({"policy": policy, "db_name": db_name}):
        return False
    if any(_matches(item, db_name, table) for item in policy["denied_tables"]):
        return False
    if policy["allow_all_tables"]:
        return True
    return any(_matches(item, db_name, table) for item in policy["allowed_tables"])


def sanitize_model_db_config(params: dict) -> dict:
    """模型自传的 db_config 只保留非连接字段；连接由服务端注入。参数：policy / db_config。"""
    policy = params["policy"]
    config = dict(params.get("db_config") or {})
    if not policy["allow_model_db_config"]:
        for key in ("host", "port", "user", "password", "path", "dir"):
            config.pop(key, None)
    return config


def apply_db_policy(params: dict) -> dict:
    """把默认库/表白名单与写开关压到已合并的 db_config 上。参数：policy / db_config。"""
    policy = params["policy"]
    config = dict(params.get("db_config") or {})
    config["allow_write"] = bool(policy["allow_write"] and config.get("allow_write", True))
    config["allowed_databases"] = policy["allowed_databases"]
    config["allowed_tables"] = policy["allowed_tables"]
    config["denied_databases"] = policy["denied_databases"]
    config["denied_tables"] = policy["denied_tables"]
    return config
