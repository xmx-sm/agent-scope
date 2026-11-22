# backend CODE_INDEX

后端文件级索引：目录、行数、符号、依赖与路由映射。找文件、改代码前先在此定位。

- 代码规模：`app/` 下约 **2300 行 / 55 个 Python 文件**（含 `__init__`）
- 分层：`routers`（解析）→ `services/<domain>`（执行）→ `core` / `models` / `schemas`（基础设施）
- 行数会随迭代变化，以 `wc -l` 为准；本表用于定位而不是精确统计

---

## 一、入口与基础设施

| 文件 | 行数 | 符号 | 职责 |
|---|---:|---|---|
| `app/main.py` | 98 | `lifespan`、`api_error_handler`、`validation_error_handler`、`integrity_error_handler` | 应用装配、CORS、异常信封、路由挂载 |
| `app/core/config.py` | 50 | `Settings`、`get_settings` | pydantic-settings 读取 `.env` |
| `app/core/database.py` | 39 | `Base`、`engine`、`AsyncSessionLocal`、`get_db`、`init_db`、`close_db` | 异步引擎、建表、`avatar` 幂等迁移 |
| `app/core/security.py` | 75 | `hash_password`、`verify_password`、`create_token`、`decode_token` | scrypt 哈希 + JWT |
| `app/core/deps.py` | 101 | `ApiError`、`ok`、`user_public`、`get_current_user`、`require_super_admin`、`require_permission` | 鉴权依赖与统一响应 |
| `app/core/permissions.py` | 42 | `PERMISSIONS`、`ALL_PERMISSION_KEYS`、`ASSIGNABLE_PERMISSION_KEYS`、`DEFAULT_ROLE_PERMISSIONS`、`ROLE_LABELS`、`ROLES` | 权限点单一真相源 |
| `app/core/seed.py` | 127 | `SEED_USERS`、`SEED_PASSWORD`、`async_seed` | 种子账号、配置、角色权限与升级兼容 |

### core/deps.py 依赖

```
deps → core.database (get_db)
     → core.security (decode_token)
     → services.permissions.evaluate (require_permission 内延迟导入，避免成环)
```

---

## 二、模型与请求体

| 文件 | 行数 | 符号 |
|---|---:|---|
| `app/models/common.py` | 12 | `new_id`、`utc_now` |
| `app/models/user.py` | 58 | `User`、`UserPermissionState` |
| `app/models/system.py` | 37 | `SystemConfig`、`RolePermission` |
| `app/models/__init__.py` | 14 | 统一导出 |
| `app/schemas/auth.py` | 25 | `RegisterIn`、`LoginIn`、`RefreshIn`、`ChangePasswordIn` |
| `app/schemas/user.py` | 36 | `ProfileUpdateIn`、`UserCreateIn`、`UserUpdateIn`、`ResetPasswordIn` |
| `app/schemas/permission.py` | 18 | `PermissionUpdateIn`、`TempGrantIn`、`UserPermissionUpdateIn` |
| `app/schemas/config.py` | 9 | `ConfigUpdateIn` |

依赖方向：`models → core.database`；`schemas` 不依赖业务层。

---

## 三、路由层 `app/routers/`

路由层只做参数解析与响应包装，业务全部下沉到同名服务包。

| 文件 | 行数 | 接口前缀 | 对应服务 |
|---|---:|---|---|
| `auth.py` | 72 | `/auth` | `services/auth/` |
| `user.py` | 101 | `/profile`、`/admin/users*`、`/admin/stats` | `services/user/` |
| `config.py` | 38 | `/admin/configs` | `services/config/` |
| `permissions.py` | 109 | `/permissions/*`、`/admin/permissions*`、`/admin/users/*/permissions` | `services/permissions/` |
| `system.py` | 29 | `/health`、`/public/site`、`/system/status` | `services/system/` |

### 路由与服务函数映射

| 路由函数 | 服务函数 |
|---|---|
| `auth.register` | `auth.register.async_register` |
| `auth.login` | `auth.login.async_login` |
| `auth.refresh` | `auth.token.async_refresh` |
| `auth.me` | `auth.token.async_me_payload` |
| `auth.change_password` | `auth.password.async_change_password` |
| `user.update_profile` | `user.profile.async_update_profile` |
| `user.stats` | `user.query.async_stats` |
| `user.list_users` | `user.query.async_list_users` |
| `user.create_user` | `user.command.async_create_user` |
| `user.update_user` | `user.command.async_update_user` |
| `user.delete_user` | `user.command.async_delete_user` |
| `user.reset_password` | `user.command.async_reset_password` |
| `config.list_configs` | `config.service.async_list_configs` |
| `config.update_config` | `config.service.async_update_config` |
| `config.reset_config` | `config.service.async_reset_config` |
| `permissions.my_permissions` | `permissions.evaluate.async_permission_detail` |
| `permissions.shrink_mine` | `permissions.shrink.async_shrink_self` |
| `permissions.team_permissions` | `permissions.team.async_team_permissions` |
| `permissions.shrink_member` | `permissions.shrink.async_shrink_member` |
| `permissions.user_permissions` | `permissions.admin.async_user_permission_detail` |
| `permissions.set_user_permissions` | `permissions.admin.async_set_user_permissions` |
| `permissions.list_permissions` | `permissions.role.async_list_permissions` |
| `permissions.update_permissions` | `permissions.role.async_update_permissions` |
| `system.site_info` | `system.site.async_site_info` |
| `system.system_status` | `system.status.async_status` |

---

## 四、服务层 `app/services/`

所有服务入口只接收一个字典参数（见《参数说明.md》）。

### 4.1 `services/auth/` — 对应 `routers/auth.py`

| 文件 | 行数 | 符号 | 依赖 |
|---|---:|---|---|
| `login.py` | 48 | `async_login` | `rate_limit`、`token`、`user.common`、`config.service` |
| `register.py` | 77 | `async_register` | `rate_limit`、`token`、`user.common`、`config.service` |
| `token.py` | 47 | `async_issue_tokens`、`async_refresh`、`async_me_payload` | `core.security`、`permissions.evaluate` |
| `password.py` | 28 | `async_change_password` | `core.security`、`config.service` |
| `rate_limit.py` | 32 | `async_rate_limit` | `config.service`、`utils.rate_limiter` |

### 4.2 `services/user/` — 对应 `routers/user.py`

| 文件 | 行数 | 符号 | 依赖 |
|---|---:|---|---|
| `common.py` | 54 | `clean_optional`、`async_assert_unique`、`async_find_by_identifier` | `core.deps` |
| `query.py` | 86 | `async_get_user_or_404`、`async_list_users`、`async_stats` | `core.permissions` |
| `command.py` | 179 | `async_create_user`、`async_update_user`、`async_delete_user`、`async_reset_password` | `user.common`、`core.security` |
| `profile.py` | 57 | `async_update_profile` | `user.common` |
| `tree.py` | 41 | `async_descendants`、`async_is_descendant` | `models.User` |

### 4.3 `services/config/` — 对应 `routers/config.py`

| 文件 | 行数 | 符号 | 依赖 |
|---|---:|---|---|
| `meta.py` | 41 | `CONFIG_DEFINITIONS`、`CONFIG_BY_KEY` | `core.config` |
| `service.py` | 117 | `async_get_config`、`async_list_configs`、`async_update_config`、`async_reset_config` | `config.meta` |

### 4.4 `services/permissions/` — 对应 `routers/permissions.py`

| 文件 | 行数 | 符号 | 依赖 |
|---|---:|---|---|
| `common.py` | 58 | `load_list`、`load_temp`、`parse_expire`、`is_expired` | `core.deps` |
| `state.py` | 46 | `async_get_state`、`split_state`、`dump_list` | `permissions.common` |
| `evaluate.py` | 49 | `async_permission_detail`、`async_effective_permissions` | `role`、`state`、`core.permissions` |
| `shrink.py` | 82 | `async_shrink_self`、`async_shrink_member`（内部 `_async_add_shrink`） | `evaluate`、`state`、`user.tree` |
| `team.py` | 32 | `async_team_permissions` | `evaluate`、`user.tree` |
| `role.py` | 74 | `async_role_permissions`、`async_list_permissions`、`async_update_permissions` | `models.RolePermission` |
| `admin.py` | 86 | `async_admin_set_state`、`async_user_permission_detail`、`async_set_user_permissions` | `evaluate`、`state`、`user.query` |

### 4.5 `services/system/` — 对应 `routers/system.py`

| 文件 | 行数 | 符号 | 依赖 |
|---|---:|---|---|
| `site.py` | 24 | `async_site_info` | `config.service` |
| `status.py` | 17 | `async_status` | `system.monitor`、`utils.rate_limiter` |
| `monitor.py` | 268 | `async_system_status`、`_cpu_info`、`_memory_info`、`_disk_info`、`_network_info`、`_gpu_info`、`_process_info`、`_redis_info`、`_database_info` | psutil、SQLAlchemy、Redis |

---

## 五、工具层 `app/utils/`

| 文件 | 行数 | 符号 | 说明 |
|---|---:|---|---|
| `redis_util.py` | 79 | `async_redis_reachable`、`async_create_redis_client`、`async_get_redis_client`、`async_close_redis` | 1 秒 TCP 探活，不可用降级 |
| `rate_limiter.py` | 93 | `RateLimiter.check`、`clear`、`list_buckets`、`rate_limiter` | Redis zset 滑动窗口，失败降级进程内 |

---

## 六、依赖方向

```text
routers ──► services/<domain> ──► core (config/database/security/deps/permissions)
                              └─► models
                              └─► utils (redis / rate_limiter)

core.deps.require_permission ──► services.permissions.evaluate（函数内延迟导入）
core.seed ──► services.config.meta / core.permissions
```

禁止反向依赖：

- `services/` 不导入 `routers/`
- `models/` 不导入 `services/`
- `utils/` 只依赖 `core.config`，不依赖业务域

---

## 七、新增功能的固定步骤

1. 在 `schemas/` 增加请求体（如需要）。
2. 在 `routers/<domain>.py` 增加路由，只做解析与响应包装。
3. 在 `services/<domain>/` 增加处理文件或扩展现有文件，函数接收单个 `params` 字典。
4. 如新增权限点，改 `core/permissions.py` 并在 `routers` 上挂 `require_permission`。
5. 同步《参数说明.md》《接口说明.md》《CODE_INDEX.md》和《开发记录.md》。

---

## 八、v0.3.0 新增：菜单与 AI/邮箱配置

| 文件 | 行数 | 符号 | 职责 |
|---|---:|---|---|
| `app/models/menu.py` | 35 | `Menu` | 可配置菜单（两级、图标、排序、权限点、可见性） |
| `app/schemas/menu.py` | 30 | `MenuCreateIn`、`MenuUpdateIn`、`MenuReorderIn` | 菜单请求模型 |
| `app/routers/menu.py` | 55 | `my_menus`、`list_menus`、`create_menu`、`update_menu`、`delete_menu`、`reorder_menus` | 菜单路由 |
| `app/services/menu/query.py` | 84 | `menu_public`、`async_list_all`、`async_mine` | 菜单读取与按有效权限过滤 |
| `app/services/menu/command.py` | 128 | `async_create_menu`、`async_update_menu`、`async_delete_menu`、`async_reorder_menus` | 菜单写操作与排序 |
| `app/services/system/email.py` | 61 | `async_send_email` | 按 `mail.*` 配置发送邮件 |
| `app/utils/mask.py` | 19 | `SENTINEL`、`mask_secret`、`is_sentinel` | 密钥脱敏与回写哨兵 |
| `app/schemas/email.py` | 11 | `EmailSendIn` | 测试邮件请求体 |

### 新增路由 ↔ 服务映射

| 路由 | 服务 |
|---|---|
| `GET /menus/mine` | `menu.query.async_mine` |
| `GET /admin/menus` | `menu.query.async_list_all` |
| `POST /admin/menus` | `menu.command.async_create_menu` |
| `PUT /admin/menus/{id}` | `menu.command.async_update_menu` |
| `DELETE /admin/menus/{id}` | `menu.command.async_delete_menu` |
| `POST /admin/menus/reorder` | `menu.command.async_reorder_menus` |
| `POST /admin/email/test` | `system.email.async_send_email` |

菜单可见性：`super_only` 先按角色过滤，再按 `permission` 与用户**有效权限**过滤；分组没有可见子菜单时整组隐藏。
