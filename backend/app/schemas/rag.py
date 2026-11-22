"""知识库请求模型。"""

from pydantic import BaseModel, Field


class RagSearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    collection: str = "default"
    top_k: int = 5
