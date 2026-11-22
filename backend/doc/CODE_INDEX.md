# backend CODE_INDEX

后端文件级索引。**目录职责与新增功能落位以 [项目结构.md](./项目结构.md) 为准。**

## 一、入口与基础设施

| 文件 | 职责 |
|---|---|
| `app/main.py` | 应用装配、生命周期、异常信封、聚合路由挂载 |
| `app/core/config.py` | `.env` 配置 |
| `app/core/database.py` | 异步引擎、建表、幂等补列 |
| `app/core/security.py` | scrypt 密码哈希、JWT |
| `app/core/deps.py` | 鉴权依赖、统一响应、ApiError |
| `app/core/permissions.py` | 权限点单一真相源 |
| `app/core/seed.py` | 种子账号、配置、角色权限、菜单布局迁移 |

> 全部服务函数的入参与功能说明见 [服务函数索引.md](./服务函数索引.md)。
| `app/core/tools.py` | AI 工具目录 |
| `app/utils/mask.py` | 密钥脱敏与 `******` 回写哨兵 |
| `app/utils/redis_util.py` | Redis 探活与客户端 |
| `app/utils/rate_limiter.py` | Redis 滑动窗口限流，降级进程内 |

## 二、领域目录

```text
models/
├── account/      user.py
├── access/       tools.py
├── system/       config.py, menu.py
└── agent/        conversation, config, knowledge, collaboration, automation, resources

schemas/
├── account/      auth.py, user.py, permission.py
├── access/       tool.py, tool_approval.py, tool_config.py, security.py
├── system/       config.py, menu.py
├── integrations/ email.py
└── agent/        chat, conversation, config, knowledge, collaboration, automation, resources

routers/
├── account/      auth.py, user.py
├── access/       permissions.py, tools.py
├── system/       system.py, config.py, menu.py
└── agent/        chat, config, knowledge, resources, collaboration, automation, media, admin, public_a2a

services/
├── account/      auth/, user/
├── access/       permissions/, tools/, security/
├── system/       monitor.py, status.py, site.py
├── config/       meta.py, service.py
├── menu/         query.py, command.py, prefs.py
├── llm/          providers.py
├── integrations/ email.py
└── agent/        runtime/, conversation/, knowledge/, resources/, collaboration/, automation/, media/, config/, analytics/
```

## 三、路由与服务映射

| Router | Service |
|---|---|
| `routers/account/auth.py` | `services/account/auth/` |
| `routers/account/user.py` | `services/account/user/` |
| `routers/access/permissions.py` | `services/access/permissions/` |
| `routers/access/tools.py` | `services/access/tools/` |
| `routers/system/system.py` | `services/system/`、`services/integrations/email.py` |
| `routers/system/config.py` | `services/config/`、`services/llm/` |
| `routers/system/menu.py` | `services/menu/` |
| `routers/agent/chat.py` | `services/agent/conversation/`、`services/agent/analytics/` |
| `routers/agent/config.py` | `services/agent/config/`、`services/llm/` |
| `routers/agent/knowledge.py` | `services/agent/knowledge/` |
| `routers/agent/resources.py` | `services/agent/resources/` |
| `routers/agent/collaboration.py` | `services/agent/collaboration/` |
| `routers/agent/automation.py` | `services/agent/automation/` |
| `routers/agent/media.py` | `services/agent/media/` |
| `routers/agent/public_a2a.py` | `services/agent/collaboration/a2a.py` |
| `routers/agent/admin.py` | `services/agent/analytics/` |

## 四、依赖方向

```text
routers → services → core / models / utils
models  → core
schemas → pydantic only
```

禁止：

- `services/` 反向导入 `routers/`
- `models/` 导入 `services/`
- 在领域包根目录继续平铺无关文件

## 五、新增功能检查清单

1. 确定领域与子域。
2. 模型放 `models/<领域>/`。
3. 请求体放 `schemas/<领域>/`。
4. 路由放 `routers/<领域>/`，只解析参数。
5. 业务放 `services/<领域>/`，函数只收一个 `params: dict`。
6. 新表/列同步 `core/database.py` 与《数据库说明.md》。
7. 更新《项目结构.md》《参数说明.md》《接口说明.md》《开发记录.md》。
