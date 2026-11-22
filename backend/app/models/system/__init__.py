"""系统配置、角色权限与菜单模型。"""

from app.models.system.config import RolePermission, SystemConfig
from app.models.system.menu import Menu, UserMenuPref

__all__ = ["SystemConfig", "RolePermission", "Menu", "UserMenuPref"]
