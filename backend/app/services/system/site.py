"""站点公开信息。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config.service import async_get_config


async def async_site_info(params: dict) -> dict:
    """参数：session"""
    session: AsyncSession = params["session"]
    return {
        "site_name": await async_get_config(
            {"session": session, "key": "site_name", "default": "Agent Scope Platform"}
        ),
        "site_description": await async_get_config(
            {"session": session, "key": "site_description", "default": ""}
        ),
        "allow_register": await async_get_config(
            {"session": session, "key": "allow_register", "default": True}
        ),
        "default_avatar": await async_get_config(
            {"session": session, "key": "default_avatar", "default": ""}
        ),
    }
