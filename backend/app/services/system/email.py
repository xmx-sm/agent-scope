"""邮件发送服务：默认配置来自 system_configs 的 mail.* 项。"""

from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.services.config.service import async_get_config


async def _config(params: dict):
    return await async_get_config(params)


async def async_send_email(params: dict) -> dict:
    """参数：session / to / subject / content"""
    session: AsyncSession = params["session"]
    to: str = str(params["to"]).strip()
    subject: str = str(params.get("subject") or "Agent Scope 测试邮件")
    content: str = str(params.get("content") or "这是一封来自 Agent Scope 的测试邮件。")

    if "@" not in to:
        raise ApiError("收件人邮箱格式不正确")

    host = str(await _config({"session": session, "key": "mail.smtp.host", "default": ""}) or "").strip()
    port = int(await _config({"session": session, "key": "mail.smtp.port", "default": 465}))
    user = str(await _config({"session": session, "key": "mail.smtp.user", "default": ""}) or "").strip()
    password = str(await _config({"session": session, "key": "mail.smtp.password", "default": ""}) or "")
    from_address = str(await _config({"session": session, "key": "mail.from_address", "default": ""}) or "").strip() or user
    from_name = str(await _config({"session": session, "key": "mail.from_name", "default": "Agent Scope"}) or "Agent Scope")
    use_tls = bool(await _config({"session": session, "key": "mail.use_tls", "default": True}))
    timeout = int(await _config({"session": session, "key": "mail.connect_timeout", "default": 30}))

    if not host:
        raise ApiError("请先在默认设置 → 邮箱中配置 SMTP 服务器")
    if not from_address:
        raise ApiError("请先配置 SMTP 账号或发件地址")

    message = EmailMessage()
    message["From"] = formataddr((from_name, from_address))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(content)

    try:
        await aiosmtplib.send(
            message,
            hostname=host,
            port=port,
            username=user or None,
            password=password or None,
            timeout=timeout,
            use_tls=(use_tls and port == 465),
            start_tls=(use_tls and port != 465),
        )
    except Exception as exc:  # noqa: BLE001
        raise ApiError(f"邮件发送失败：{exc}")

    return {"to": to, "subject": subject, "from": from_address}
