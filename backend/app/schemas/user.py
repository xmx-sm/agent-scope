"""用户资料与用户管理请求模型。"""

from pydantic import BaseModel, Field


class ProfileUpdateIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    avatar: str | None = Field(default=None, max_length=500)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=64)
    nickname: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    role: str = "user"
    leader_id: str | None = None
    is_active: bool = True
    avatar: str | None = Field(default=None, max_length=500)


class UserUpdateIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    role: str | None = None
    leader_id: str | None = None
    is_active: bool | None = None
    avatar: str | None = Field(default=None, max_length=500)


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=64)
