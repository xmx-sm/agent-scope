"""权限点与角色默认权限。

super_only 的权限点只属于超级管理员，不参与角色权限矩阵；
其余权限点可由超管在矩阵中授予角色，并允许上级/本人在此基础上继续收缩。
"""

PERMISSIONS: list[dict] = [
    {"key": "dashboard", "name": "工作台", "group": "基础"},
    {"key": "profile", "name": "个人中心", "group": "基础"},
    {"key": "permissions.self", "name": "我的权限", "group": "权限"},
    {"key": "permissions.team", "name": "团队权限", "group": "权限"},
    {"key": "ai.use", "name": "使用 AI", "group": "AI"},
    {"key": "ai.config", "name": "AI 配置管理", "group": "AI", "super_only": True},
    {"key": "admin.users", "name": "用户管理", "group": "管理", "super_only": True},
    {"key": "admin.settings", "name": "默认设置", "group": "管理", "super_only": True},
    {"key": "admin.permissions", "name": "权限配置", "group": "管理", "super_only": True},
    {"key": "admin.menus", "name": "菜单配置", "group": "管理", "super_only": True},
    {"key": "admin.audits", "name": "权限审计", "group": "管理", "super_only": True},
    {"key": "system.status", "name": "运行状态", "group": "管理", "super_only": True},
]

ALL_PERMISSION_KEYS = [item["key"] for item in PERMISSIONS]

# 可分配给普通角色的权限点（超管专属项不进入矩阵）
ASSIGNABLE_PERMISSION_KEYS = [item["key"] for item in PERMISSIONS if not item.get("super_only")]

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": ALL_PERMISSION_KEYS,
    "admin": ["dashboard", "profile", "permissions.self", "permissions.team", "ai.use"],
    "user": ["dashboard", "profile", "permissions.self", "ai.use"],
}

ROLE_LABELS: dict[str, str] = {
    "super_admin": "超级管理员",
    "admin": "管理员",
    "user": "普通用户",
}

ROLES = list(ROLE_LABELS.keys())


def permission_name(key: str) -> str:
    for item in PERMISSIONS:
        if item["key"] == key:
            return item["name"]
    return key
