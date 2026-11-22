"""Agent 对话请求模型。"""

from pydantic import BaseModel, Field


class ConversationCreateIn(BaseModel):
    title: str = Field(default="新会话", max_length=200)


class ChatStreamIn(BaseModel):
    conversation_id: str
    content: str = Field(min_length=1, max_length=100000)
    attachment_ids: list[str] = Field(default_factory=list)


class TtsIn(BaseModel):
    text: str
    voice: str = ""
    model: str = ""
