"""系统配置请求模型。"""

from typing import Any

from pydantic import BaseModel


class ConfigUpdateIn(BaseModel):
    value: Any
