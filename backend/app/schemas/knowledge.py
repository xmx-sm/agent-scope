"""知识库请求模型。"""

from typing import Any

from pydantic import BaseModel, Field


class LibraryCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    vector_type: str = "sqlite"
    description: str = ""
    embedding: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class LibraryUpdateIn(BaseModel):
    description: str | None = None
    embedding: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    status: str | None = None


class KnowledgeSearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    library_ids: list[str] = Field(default_factory=list)
    top_k: int = 5
    score_threshold: float | None = None
