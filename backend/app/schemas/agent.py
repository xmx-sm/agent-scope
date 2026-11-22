"""Agent 模型配置请求模型。"""

from pydantic import BaseModel


class ModelFetchIn(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    key_config: str = ""


class UserAgentConfigIn(BaseModel):
    use_system_default: bool = False
    provider: str = "openai-compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    context_window: int = 131072
    stream: bool = True
    system_prompt: str = ""
