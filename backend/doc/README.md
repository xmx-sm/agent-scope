# backend/docs

后端配套文档。按用途查，不必通读。

| 文档 | 什么时候读 | 内容 |
|---|---|---|
| [接口说明.md](./接口说明.md) | 前后端联调 / 新增接口前 | 全部 HTTP 接口、请求体、响应结构、错误码 |
| [参数说明.md](./参数说明.md) | 改服务层 / 调服务函数前 | 路由与服务的对应关系、**所有服务函数的字典参数键**、返回契约 |
| [CODE_INDEX.md](./CODE_INDEX.md) | 找文件 / 改代码前 | 目录、文件行数、符号清单、依赖方向、路由映射 |
| [配置说明.md](./配置说明.md) | 部署 / 改默认值前 | `.env` 变量、数据库、Redis、系统配置项、权限模型参数 |
| [数据库说明.md](./数据库说明.md) | 改表 / 排查数据问题前 | 表结构、种子数据、迁移约定 |
| [踩坑记录.md](./踩坑记录.md) | 报错时 / 重构前 | 本项目实际踩过的坑、误诊与修复依据 |
| [开发记录.md](./开发记录.md) | 了解进度 | 版本进度、设计决策、已知限制 |

## 三十秒上手

```bash
cd backend
cp .env.example .env
../.venv/bin/python run.py
```

```python
# 服务层统一字典传参
await user_query.async_list_users({
    "session": db,
    "page": 1,
    "page_size": 10,
    "keyword": "",
    "role": "",
    "viewer": operator,
})
```

关键约定：

1. **路由层只解析**：`app/routers/*.py` 不写业务。
2. **服务层按域拆包**：`app/services/<domain>/`，与路由文件同名。
3. **服务函数只收一个字典**：键名见《参数说明.md》。
4. **身份只信 JWT**：不读前端传入的 user_id。
5. **响应统一**：`{"code": 200, "data": ..., "msg": "success"}`。

## 技术栈

- Python 3.12+（当前运行于仓库根 `.venv`，Python 3.14.8）
- FastAPI / Uvicorn
- SQLAlchemy 2.x async + asyncpg
- PostgreSQL 17
- PyJWT（HS256）+ scrypt 密码哈希
- Redis 滑动窗口限流（不可用自动降级进程内）
- psutil / nvidia-smi 运行状态采集

## 本地启动

```bash
# 仓库根目录
uv pip install --python .venv/bin/python -r backend/requirements.txt

cd backend
cp .env.example .env          # 按需修改数据库账号、JWT_SECRET、Redis
../.venv/bin/python run.py    # http://127.0.0.1:8000 ，文档 /docs
```

数据库不存在时先创建：

```bash
PGPASSWORD=990108 psql -h 127.0.0.1 -U mx -d postgres \
  -c "CREATE DATABASE agent_scope OWNER mx"
```

首次启动自动建表并写入种子数据（幂等）：

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
├── models/                    # ORM 模型
├── schemas/                   # 请求模型
├── routers/                   # 只有路由文件：声明路径、解析参数、调服务
├── services/                  # 业务执行，按域拆包
│   ├── auth/                  # 对应 routers/auth.py
│   ├── user/                  # 对应 routers/user.py
│   ├── config/                # 对应 routers/config.py
│   ├── permissions/           # 对应 routers/permissions.py
│   └── system/                # 对应 routers/system.py
└── utils/                     # Redis / 限流
```

文件级索引与行数见 [CODE_INDEX.md](./CODE_INDEX.md)。

## 分层约定

1. `routers/<domain>.py` 只做三件事：声明路径与方法、解析参数/依赖、调用 `services/<domain>/` 并包装响应。
2. `services/<domain>/` 是路由对应的业务包；按职责拆文件，避免单文件过长。
3. 路由文件与同名服务文件夹一一对应：`routers/user.py` ↔ `services/user/`。
4. 跨域复用逻辑放在对应域包内（如 `services/permissions/evaluate.py`），不要复制。
5. `core/` 只放基础设施；`models/`、`schemas/` 按领域拆文件。
6. 新增接口固定动作：`routers/x.py` 加路由 → `services/x/` 下新增或扩展处理文件。

## 服务层字典传参约定

服务层函数只接收一个字典，便于统一日志、调试和后续扩展：

```python
result = await user_query.async_list_users({
    "session": db,
    "page": page,
    "page_size": page_size,
    "keyword": keyword,
    "role": role,
    "viewer": operator,
})
```

| 键 | 说明 |
|---|---|
| `session` | 必填，SQLAlchemy AsyncSession |
| `user` / `viewer` / `operator` / `actor` | 当前操作人对象 |
| `data` | 已校验的请求体字典 |
| 其他键 | 该业务函数的显式输入 |

例外：FastAPI 路由处理函数（框架依赖注入要求显式参数）、纯工具函数（`clean_optional`、`parse_expire` 等）、无入参的系统采集函数。

每个函数的完整键表见 [参数说明.md](./参数说明.md)。
