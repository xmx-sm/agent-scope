"""权限相关请求模型。"""

from pydantic import BaseModel


class PermissionUpdateIn(BaseModel):
    permissions: list[str]


class TempGrantIn(BaseModel):
    permission: str
    expires_at: str


class UserPermissionUpdateIn(BaseModel):
    granted: list[str] | None = None
    shrunk: list[str] | None = None
    temp_grants: list[TempGrantIn] | None = None
