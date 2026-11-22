"""请求模型统一出口。"""

from app.schemas.agent import ModelFetchIn
from app.schemas.auth import ChangePasswordIn, LoginIn, RefreshIn, RegisterIn
from app.schemas.config import ConfigUpdateIn
from app.schemas.email import EmailSendIn
from app.schemas.menu import MenuCreateIn, MenuPrefIn, MenuReorderIn, MenuUpdateIn
from app.schemas.permission import PermissionUpdateIn, TempGrantIn, UserPermissionUpdateIn
from app.schemas.security import DbAccessCheckIn
from app.schemas.tool import ToolItemIn, ToolNarrowIn, ToolPolicyIn, ToolSetIn
from app.schemas.user import ProfileUpdateIn, ResetPasswordIn, UserCreateIn, UserUpdateIn

__all__ = [
    "RegisterIn",
    "ModelFetchIn",
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
    "MenuPrefIn",
    "PermissionUpdateIn",
    "TempGrantIn",
    "UserPermissionUpdateIn",
    "ToolItemIn",
    "ToolSetIn",
    "ToolNarrowIn",
    "ToolPolicyIn",
    "DbAccessCheckIn",
]
