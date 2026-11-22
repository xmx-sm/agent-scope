"""请求模型统一出口。"""

from app.schemas.auth import ChangePasswordIn, LoginIn, RefreshIn, RegisterIn
from app.schemas.config import ConfigUpdateIn
from app.schemas.email import EmailSendIn
from app.schemas.menu import MenuCreateIn, MenuReorderIn, MenuUpdateIn
from app.schemas.permission import PermissionUpdateIn, TempGrantIn, UserPermissionUpdateIn
from app.schemas.user import ProfileUpdateIn, ResetPasswordIn, UserCreateIn, UserUpdateIn

__all__ = [
    "RegisterIn",
    "LoginIn",
    "RefreshIn",
    "ChangePasswordIn",
    "ProfileUpdateIn",
    "UserCreateIn",
    "UserUpdateIn",
    "ResetPasswordIn",
    "ConfigUpdateIn",
    "EmailSendIn",
    "MenuCreateIn",
    "MenuUpdateIn",
    "MenuReorderIn",
    "PermissionUpdateIn",
    "TempGrantIn",
    "UserPermissionUpdateIn",
]
