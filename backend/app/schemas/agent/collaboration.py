"""超级智能体与 A2A 请求模型。"""

from pydantic import BaseModel, Field


class SuperAgentSaveIn(BaseModel):
    id: str | None = None
    name: str = "超级智能体"
    description: str = ""
    enabled: bool = False
    main: dict = Field(default_factory=dict)
    subs: list[dict] = Field(default_factory=list)


class SuperConversationIn(BaseModel):
    super_agent_id: str | None = None
    member_id: str | None = None
    role: str = "main"
    title: str | None = None


class A2APeerIn(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    endpoint: str = ""
    api_key: str = ""
    remote_name: str = ""
    direction: str = "outbound"
    protocol: str = "lite"
    protocol_config: dict = Field(default_factory=dict)
    allow_tools: bool = False
    max_calls_per_day: int = 50
    timeout_seconds: int = 120
    is_active: bool = True


class A2AInvokeIn(BaseModel):
    peer: str
    message: str
    session_hint: str = "default"


class A2AInboundIn(BaseModel):
    agent_name: str
    message: str
    session_hint: str = "default"
