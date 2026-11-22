"""Agent 安全提示词拼装。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config.service import async_get_config


async def async_build_security_prompt(params: dict) -> str:
    """构建 Agent 安全提示词

    参数：session
    """
    session: AsyncSession = params["session"]
    enabled = bool(
        await async_get_config(
            {"session": session, "key": "security.prompt_guard_enabled", "default": True}
        )
    )
    if not enabled:
        return ""
    text = str(
        await async_get_config(
            {"session": session, "key": "security.prompt_guard_text", "default": ""}
        )
        or ""
    ).strip()
    if not text:
        return ""
    return f"[安全策略]\n{text}\n"
