"""知识库请求模型。"""

from typing import Any

from pydantic import BaseModel, Field


class LibraryCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    vector_type: str = "sqlite"
    description: str = ""
    embedding: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    auto_parse: bool = False
    parse_interval: int = 300


class LibraryUpdateIn(BaseModel):
    description: str | None = None
    embedding: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    status: str | None = None
    auto_parse: bool | None = None
    parse_interval: int | None = None


class KnowledgeSearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    library_ids: list[str] = Field(default_factory=list)
    top_k: int = 5
    score_threshold: float | None = None


class LibraryShareIn(BaseModel):
    target_user_id: str
    permission: str = "read"


class ParseConfigIn(BaseModel):
    parse_concurrency: int = 2
    queue_mode: str = "fifo"
    worker_interval: int = 5



class RagSearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    collection: str = "default"
    top_k: int = 5
