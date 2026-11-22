# 后端文档

FastAPI + PostgreSQL 平台后端，提供注册、登录、用户管理、默认配置与角色权限接口。

| 文档 | 内容 |
|---|---|
| [开发记录.md](./开发记录.md) | 进度、决策、已知问题、下一步 |
| [接口说明.md](./接口说明.md) | 全部 HTTP 接口、请求/响应、错误码 |
| [数据库说明.md](./数据库说明.md) | 表结构、种子数据、变更约定 |

## 技术栈

- Python 3.12+（当前运行于仓库根 `.venv`，Python 3.14.8）
- FastAPI / Uvicorn
- SQLAlchemy 2.x async + asyncpg
- PostgreSQL 17
- PyJWT（HS256）+ scrypt 密码哈希

## 本地启动

```bash
# 仓库根目录
uv pip install --python .venv/bin/python -r backend/requirements.txt

cd backend
cp .env.example .env          # 按需修改数据库账号、JWT_SECRET
../.venv/bin/python run.py    # http://127.0.0.1:8000 ，文档 /docs
```

依赖 `.env` 中的 `DATABASE_URL`，默认：

```text
postgresql+asyncpg://mx:990108@127.0.0.1:5432/agent_scope
```

数据库不存在时先创建：

```bash
PGPASSWORD=990108 psql -h 127.0.0.1 -U mx -d postgres -c "CREATE DATABASE agent_scope OWNER mx"
```

首次启动自动建表并写入种子数据（幂等，不覆盖已有值）：

| 账号 | 密码 | 角色 |
|---|---|---|
| `MX` | `990108` | 超级管理员 |
| `张三` | `990108` | 管理员（领导） |
| `李四` | `990108` | 普通用户（上级：张三） |

## 目录

```text
backend/app/
├── main.py                    # 应用装配、生命周期、异常处理
├── core/                      # 基础设施（不写业务）
│   ├── config.py
│   ├── database.py
│   ├── security.py
│   ├── deps.py
│   ├── permissions.py         # 权限点目录
│   └── seed.py
├── models/                    # ORM 模型
│   ├── user.py
│   └── system.py
├── schemas/                   # 请求模型
│   ├── auth.py
│   ├── user.py
│   ├── permission.py
│   └── config.py
├── routers/                   # 只有路由文件：声明路径、解析参数、调服务
│   ├── auth.py                # /auth/*
│   ├── user.py                # /profile、/admin/users*、/admin/stats
│   ├── config.py              # /admin/configs*
│   ├── permissions.py         # /permissions/*、/admin/permissions*、/admin/users/*/permissions
│   └── system.py              # /health、/public/site、/system/status
├── services/
│   ├── auth/                  # 对应 routers/auth.py
│   │   ├── login.py
│   │   ├── register.py
│   │   ├── token.py
│   │   ├── password.py
│   │   └── rate_limit.py
│   ├── user/                  # 对应 routers/user.py
│   │   ├── common.py          # 清洗、唯一性、登录标识查询
│   │   ├── query.py           # 用户列表、统计
│   │   ├── command.py         # 新增、修改、删除、重置密码
│   │   ├── profile.py         # 个人资料
│   │   └── tree.py            # 汇报线下属树
│   ├── config/                # 对应 routers/config.py
│   │   ├── meta.py            # 配置定义单一真相源
│   │   └── service.py         # 读取、更新、恢复默认
│   ├── permissions/           # 对应 routers/permissions.py
│   │   ├── evaluate.py        # 有效权限计算
│   │   ├── state.py           # 用户权限状态
│   │   ├── shrink.py          # 逐级收缩
│   │   ├── admin.py           # 超管授权/临时授权
│   │   ├── team.py            # 团队权限
│   │   ├── role.py            # 角色权限矩阵
│   │   └── common.py          # JSON / 过期时间工具
│   └── system/                # 对应 routers/system.py
│       ├── site.py
│       ├── status.py
│       └── monitor.py         # CPU/内存/磁盘/GPU/网络/Redis
└── utils/
    ├── redis_util.py
    └── rate_limiter.py
```

### 分层约定

1. `routers/<domain>.py` 只做三件事：声明路径与方法、解析参数/依赖、调用 `services/<domain>/` 并包装响应。
2. `services/<domain>/` 是路由对应的业务包；按职责拆文件（查询/写入/校验/子能力），避免单文件过长。
3. 路由文件与同名的服务文件夹一一对应：`routers/user.py` ↔ `services/user/`。
4. 跨域复用逻辑放在对应域包内（如 `services/permissions/evaluate.py` 被 `deps` 和 `admin` 共同使用），不要复制。
5. `core/` 只放基础设施；`models/`、`schemas/` 按领域拆文件。
6. 新增接口固定动作：`routers/x.py` 加路由 → `services/x/` 下新增或扩展处理文件。

### 服务层字典传参约定

`services/` 下所有对路由或跨域暴露的业务函数只接收一个字典参数，便于统一日志、调试和后续扩展：

```python
# routers/user.py
result = await user_query.async_list_users({
    "session": db,
    "page": 1,
    "page_size": 10,
    "keyword": "",
    "role": "",
    "viewer": operator,
})

# services/user/query.py
async def async_list_users(params: dict) -> dict:
    session = params["session"]
    page = params.get("page", 1)
    ...
```

约定：

| 键 | 说明 |
|---|---|
| `session` | 必填，SQLAlchemy AsyncSession |
| `user` / `viewer` / `operator` / `actor` | 当前操作人对象 |
| `data` | 已校验的请求体字典 |
| 其他键 | 该业务函数的显式输入 |

例外：FastAPI 路由处理函数（框架依赖注入要求显式参数）、纯工具函数（如 `clean_optional`、`parse_expire`）以及无入参的系统采集函数保持原签名。
