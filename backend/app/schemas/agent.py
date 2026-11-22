"""Agent 模型配置请求模型。"""

from pydantic import BaseModel


class ModelFetchIn(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    key_config: str = ""
