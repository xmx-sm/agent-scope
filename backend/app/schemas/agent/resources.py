"""Agent 资源：Skills / MCP / 子智能体请求模型。"""

from typing import Any

from pydantic import BaseModel, Field


class ToggleIn(BaseModel):
    is_active: bool = True


class McpSaveIn(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    mcp_type: str = "http"
    url: str = ""
    command: str = ""
    args: list[Any] = Field(default_factory=list)
    env: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class SubagentSaveIn(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    mode: str = "auto"
    is_active: bool = True


class MemoryToggleIn(BaseModel):
    enabled: bool
