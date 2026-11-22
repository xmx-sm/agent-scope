"""子智能体请求模型。"""

from pydantic import BaseModel, Field


class SubagentSaveIn(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    mode: str = "auto"
    is_active: bool = True
