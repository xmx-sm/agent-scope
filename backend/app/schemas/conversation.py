"""会话重命名请求。"""

from pydantic import BaseModel, Field


class ConversationRenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
