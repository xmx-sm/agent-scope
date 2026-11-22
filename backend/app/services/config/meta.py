"""系统配置元数据：新增配置项只在这里登记。"""

from typing import Any

from app.core.config import settings

# key / 默认值 / 标签 / 类型 / 分组 / 说明
CONFIG_DEFINITIONS: list[dict[str, Any]] = [
    {"key": "site_name", "value": settings.app_name, "label": "站点名称",
     "type": "string", "group": "站点", "description": "显示在登录页与顶栏"},
    {"key": "site_description", "value": "轻量级权限管理平台", "label": "站点描述",
     "type": "string", "group": "站点", "description": "登录页副标题"},
    {"key": "default_avatar", "value": "", "label": "默认头像 URL",
     "type": "string", "group": "站点", "description": "用户未设置头像时的占位图，留空使用文字头像"},
    {"key": "allow_register", "value": settings.allow_register, "label": "开放注册",
     "type": "bool", "group": "账号", "description": "关闭后注册接口拒绝新用户"},
    {"key": "default_role", "value": settings.default_role, "label": "注册默认角色",
     "type": "string", "group": "账号", "description": "自助注册用户的初始角色（user/admin）"},
    {"key": "password_min_length", "value": 6, "label": "密码最小长度",
     "type": "int", "group": "账号", "description": "注册与修改密码时生效"},
    {"key": "session_expire_minutes", "value": 480, "label": "登录有效期（分钟）",
     "type": "int", "group": "账号", "description": "访问令牌过期时间，签发时读取，无需重启"},
    {"key": "maintenance_mode", "value": False, "label": "维护模式",
     "type": "bool", "group": "账号", "description": "开启后除超级管理员外禁止登录"},
    {"key": "rate_limit_enabled", "value": settings.rate_limit_enabled, "label": "启用限流",
     "type": "bool", "group": "安全", "description": "关闭后登录/注册不再限流（Redis 与进程内同时生效）"},
    {"key": "login_max_attempts", "value": 10, "label": "登录次数上限",
     "type": "int", "group": "安全", "description": "同一账号+IP 在窗口内允许的登录尝试次数"},
    {"key": "login_window_seconds", "value": 900, "label": "登录限流窗口（秒）",
     "type": "int", "group": "安全", "description": "登录限流统计窗口"},
    {"key": "register_max_attempts", "value": 5, "label": "注册次数上限",
     "type": "int", "group": "安全", "description": "同一 IP 在窗口内允许的注册次数"},
    {"key": "register_window_seconds", "value": 1800, "label": "注册限流窗口（秒）",
     "type": "int", "group": "安全", "description": "注册限流统计窗口"},
    {"key": "default_page_size", "value": 10, "label": "列表默认条数",
     "type": "int", "group": "界面", "description": "用户列表等分页的默认每页条数"},
    {"key": "status_refresh_seconds", "value": 10, "label": "运行状态刷新间隔（秒）",
     "type": "int", "group": "界面", "description": "系统运行状态页面自动刷新间隔"},
]

CONFIG_BY_KEY = {item["key"]: item for item in CONFIG_DEFINITIONS}
