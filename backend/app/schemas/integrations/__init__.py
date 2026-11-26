"""外部集成请求模型。"""

from app.schemas.integrations.bot import BotCreateIn, BotUpdateIn
from app.schemas.integrations.email import EmailSendIn

__all__ = ["BotCreateIn", "BotUpdateIn", "EmailSendIn"]
