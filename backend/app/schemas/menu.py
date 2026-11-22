"""菜单配置请求模型。"""

from pydantic import BaseModel, Field


class MenuCreateIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    parent_key: str | None = None
    title: str = Field(min_length=1, max_length=60)
    path: str = Field(default="", max_length=200)
    icon: str = Field(default="Menu", max_length=60)
    permission: str | None = None
    super_only: bool = False
    sort_order: int = 100
    is_visible: bool = True


class MenuUpdateIn(BaseModel):
    parent_key: str | None = None
    title: str | None = Field(default=None, max_length=60)
    path: str | None = Field(default=None, max_length=200)
    icon: str | None = Field(default=None, max_length=60)
    permission: str | None = None
    super_only: bool | None = None
    sort_order: int | None = None
    is_visible: bool | None = None


class MenuReorderIn(BaseModel):
    ids: list[str]
