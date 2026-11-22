"""工具连接配置请求模型。"""

from typing import Any

from pydantic import BaseModel, Field


class ToolConfigIn(BaseModel):
    use_default: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
