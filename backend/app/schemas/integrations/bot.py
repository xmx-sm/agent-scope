"""机器人管理请求模型。"""

from typing import Literal

from pydantic import BaseModel, Field


class BotCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    platform: Literal["webhook"] = "webhook"
    tools_enabled: bool = False
    timeout_seconds: int = Field(default=120, ge=5, le=600)


class BotUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    tools_enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
