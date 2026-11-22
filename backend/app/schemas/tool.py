"""AI 工具权限请求模型。"""

from pydantic import BaseModel, Field


class ToolItemIn(BaseModel):
    group: str
    tool: str = ""


class ToolSetIn(BaseModel):
    mode: str = "all"
    items: list[ToolItemIn] = Field(default_factory=list)


class ToolNarrowIn(BaseModel):
    group: str
    tool: str = ""
    enabled: bool = False
