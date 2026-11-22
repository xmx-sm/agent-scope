"""ORM 模型统一出口。"""

from app.models.common import new_id, utc_now
from app.models.menu import Menu
from app.models.system import RolePermission, SystemConfig
from app.models.user import User, UserPermissionState

__all__ = [
    "User",
    "UserPermissionState",
    "SystemConfig",
    "RolePermission",
    "Menu",
    "new_id",
    "utc_now",
]
