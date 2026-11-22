# agent_scope

基于 [AgentScope](https://github.com/agentscope-ai/agentscope) 的 Agent 框架封装项目。

> **版本：`v0.1.0`**
> **状态：AgentScope 框架层搭建完成。**
>
> 本版本完成工具、配置、模型、媒体、RAG、Agent、权限、中间件、工作区、
> 长期记忆、实时语音与统一 `async_dispatch` 入口。
> HTTP / SSE / WebSocket、会话持久化和业务 session registry 按设计交由业务后端实现。

目标是把「模型、Agent 运行循环、工具、权限审批、记忆、RAG、存储」收敛成一套可复用的框架层，
业务侧只负责配置和编排，而不是每个项目重写一遍 Agent 底座。

当前进度：**框架层搭建完成；服务化传输层由业务后端承接。**

- AgentScope：`2.0.12`
- Python：`3.14.8`
- 当前仓库只包含 `scope/`（框架与工具源码）与配套文档

---

## 一、当前进展

### 已完成

| 层 | 内容 | 规模 |
|---|---|---|
| 工具层 | 5 个通用域：db / net / mail / mcp / system + `tools/rag` | 40 文件 |
| 配置层 | `scope/config/`：SQLite 配置中心，110 项默认配置 | 4 文件 / 619 行 |
| 模型层 | `scope/llm/`：多厂商 Chat / Embedding / TTS / ASR 工厂，视频 formatter | 3 文件 |
| 媒体层 | `scope/media/`：TTS 落盘 / base64 / URL、ASR 转写、文件闸门 | 4 文件 |
| RAG 层 | `scope/rag/`：文档解析/切片/embedding、SQLite / Qdrant / Milvus / MongoDB / Elasticsearch / Zvec / OceanBase 向量库、KnowledgeBase/RAGMiddleware；`tools/rag/` 工具入口 | 14 文件 |
| 子智能体 | `scope/agent/`：主 Agent builder/runtime、上下文管理、子智能体、委派、审批、取消、Plan、Pipeline、SOP | 9 文件 |
| 权限层 | `scope/permission/`：官方 `PermissionContext` 字典构建；`sqlite/audit/pending/function_rules` 字典开关；SQLite 规则/审计/pending；函数级工具适配 | 5 文件 |
| 中间件层 | `scope/middleware/`：Tracing / Budget / TTS / ModelRouter / RAG / 长期记忆（Agentic/ReMe/Mem0）/ Steering / 自定义中间件字典工厂 | 2 文件 |
| 工作区层 | `scope/workspace/`：Local / Bubblewrap / Docker / E2B / Daytona / K8s / OpenSandbox / AppleContainer 字典工厂 | 2 文件 |
| 实时语音层 | `scope/realtime/`：DashScope / OpenAI / Gemini / xAI 实时模型、RealtimeAgent、本地音频传输 | 2 文件 |
| 后端入口 | `scope/main.py`：统一 `async_dispatch` 路由，覆盖 tool/rag/llm/media/agent/permission/middleware/workspace/realtime/config/system | 1 文件 |
| Skills | `scope/skills/`：用户自定义目录加载（`LocalSkillLoader`） | 2 文件 |

工具域能力：

| 域 | 能力 |
|---|---|
| `db` | PostgreSQL / MySQL / MongoDB / SQLite；列库、列表、表结构、分页取数、count、只读 SQL、写操作；库级/表级白名单、写影响行数上限 |
| `net` | HTTP 请求、天气、城市、下载、crawl / crawl_many / deep_crawl、截图、PDF 提取 |
| `mail` | 发信、收信、按条件查找、附件、分页 |
| `mcp` | MCP 客户端与配置解析（stdio / http） |
| `system` | Shell 命令执行 |
| `rag` | 知识库写入 / 检索 / 删除 / 文档列表；默认 SQLite 后端；文件读取过闸门 |

配置层的约定：

```
调用传入 data  >  config.db（SQLite）  >  报错 / None
```

- 连接/身份类参数（`db.type`、`db.port.*`、`db.database`、mail 的 smtp/imap host+port）
  没有源码兜底：调用与 SQLite 都没有值时返回 400「缺少参数 xxx」。
- 10 个钳制项只收紧不放宽（`clamp_get`，如查询行数上限、写影响行数上限）。
- 6 个敏感项出厂为 `None`，仅支持部署方写入 `config.db`。
- `config.db`、`.venv`、MCP 配置、向量库数据等已加入 `.gitignore`，不入库。

### 近期修复

| 项 | 内容 |
|---|---|
| A17 | IMAP 搜索表达式注入：`keyword/subject/sender` 统一转义 `\` 与 `"` |
| C2 | SQLite 文件夹模式下 `list_databases` 白名单与黑名单统一走 `_db_same` |
| A21 | `download` 与 `screenshot` 统一走 `net/_fs.py` 文件闸门 |
| 连接参数 | 去掉 `postgresql` / `5432` / `smtp.qq.com` 等硬编码兜底 |
| 文件闸门 | `net/_fs.py` 的读写闸门合并为内部 `_check_fs`，对外契约不变 |

### 待实现

```
scope/
├── agent/          # 主 Agent builder/runtime + 上下文管理 + 子智能体已实现；Toolkit 装配待完善
├── middleware/     # 已实现：Tracing / Budget / TTS / ModelRouter / RAG / Memory / Steering
├── permission/     # 已实现：PermissionContext、SQLite 规则/审计/pending、函数级规则
├── skills/         # 已实现：用户自定义 Skills 目录加载
├── storage/        # 空：会话 / 消息 / 工作区
└── main.py         # 已实现：统一 async_dispatch 后端入口；HTTP/SSE 服务待做
```

> `llm/`、`media/`、`rag/`、`permission/` 已实现；`agent/` 的子智能体与主 Agent runtime 已实现。
> 详见 [docs/框架层规划.md](scope/docs/框架层规划.md) 第三节-B/三-C/三-D/三-E。

框架层缺口、目标结构、审批与 RAG 的详细设计见
[docs/框架层规划.md](scope/docs/框架层规划.md)。

---

## 二、目录结构

```text
agent_scope/
├── README.md                    # 本文件
├── .gitignore
└── scope/
    ├── main.py                  # 统一 async_dispatch 后端入口
    ├── config/                  # SQLite 配置中心
    │   ├── schema.py            # 110 项配置的单一真相源
    │   ├── store.py             # 读写 + 进程级缓存 + 生命周期 API
    │   ├── merge.py             # pick / pick_str / pick_int
    │   └── __init__.py
    ├── common/                  # 跨层文件闸门
    │   ├── fs.py                # check_read/check_write
    │   └── __init__.py
    ├── agent/                   # 主 Agent 与子智能体
    │   ├── builder.py           # 主 Agent 装配（模型/Toolkit/上下文）
    │   ├── context.py           # 上下文压缩 / 运行时注入 / 卸载
    │   ├── runtime.py           # 主 Agent 事件流 / 审批 / 中断
    │   ├── plan.py              # 计划模式 TaskCreate/Get/List/Update
    │   ├── pipeline.py          # GoalPipeline / TeamPipeline 构建
    │   ├── sop.py               # SOP / SOPEngine 构建与状态持久化
    │   ├── subagents.py         # spec 校验 / 工具解析 / 工具组权限
    │   ├── delegate.py          # 独立 AgentState 执行 / 委派工具
    │   └── __init__.py
    ├── permission/              # 权限系统（官方 PermissionContext）
    │   ├── context.py           # 字典 → PermissionContext / 模式切换
    │   ├── bundle.py            # 统一权限字典与开关
    │   ├── tool.py              # 按 data["function"] 细分的 FunctionTool
    │   ├── store.py             # SQLite 规则 / 审计 / pending
    │   └── __init__.py
    ├── middleware/              # 官方 Agent 中间件
    │   ├── factory.py           # 字典 → Tracing/Budget/TTS/ModelRouter/RAG/长期记忆
    │   └── __init__.py
    ├── workspace/               # 官方工作区
    │   ├── factory.py           # Local/Docker/Bubblewrap/E2B/K8s/... 字典工厂
    │   └── __init__.py
    ├── realtime/                # 实时语音
    │   ├── factory.py           # RealtimeModel / RealtimeAgent / Transport
    │   └── __init__.py
    ├── llm/                     # 模型工厂（Chat / Embedding / TTS / ASR）
    │   ├── agent_model.py       # 对外入口
    │   ├── _factory.py          # 内部注册表与构造器
    │   ├── formatters.py        # 视频输入 formatter
    │   └── __init__.py
    ├── media/                   # 生成类模型的 I/O 服务
    │   ├── tts.py               # 文本 → 音频 → 文件/base64/URL
    │   ├── asr.py               # 音频 → 文本（可选落盘）
    │   ├── fs.py                # 读/写文件闸门
    │   └── __init__.py
    ├── rag/                     # RAG 知识库
    │   ├── common.py            # 解析 / 切片 / embedding
    │   ├── sqlite_db.py         # 本地 SQLite 向量库（工具后端）
    │   ├── sqlite_vector_store.py # 官方 VectorStoreBase 适配
    │   ├── vector_store_factory.py # Qdrant/Milvus/Mongo/ES/Zvec/OceanBase
    │   ├── zvec_store.py        # Zvec BM25 / embedding / hybrid
    │   ├── oceanbase_store.py   # OceanBase / pyobvector 适配
    │   ├── kb_db.py             # 通用 KnowledgeBase 直连后端
    │   ├── knowledge.py         # KnowledgeBase / RAGMiddleware 工厂
    │   ├── registry.py          # 向量模型标注注册表
    │   ├── config.py            # data > config.db > 默认/400
    │   ├── rag_main.py          # 后端分发
    │   └── __init__.py
    ├── skills/                  # 用户自定义 Skills
    │   ├── loader.py
    │   └── __init__.py
    ├── tools/
    │   ├── rag/                 # RAG 工具入口 async_rag_tools
    │   ├── db/                  # 数据库工具（四层结构：_helper → executors → dialect → 方言入口）
    │   ├── net/                 # 网络工具（基础请求 + 浏览器渲染/截图/PDF）
    │   ├── mail/                # 邮件工具（IMAP / SMTP）
    │   ├── mcp/                 # MCP 客户端
    │   └── system/              # Shell 命令
    └── docs/
        ├── README.md            # 文档导航
        ├── 参数说明.md          # 各工具入口签名、入参、返回契约
        ├── CODE_INDEX.md        # 文件 / 符号 / 依赖图
        ├── 工具拆分规范.md      # 组织规则与验证方法
        ├── 踩坑记录.md          # 使用侧坑、集成坑、误诊纠正
        ├── 配置说明.md          # 110 项配置与生命周期
        └── 框架层规划.md        # 框架层缺口、审批/RAG 设计、路线图
```

---

## 三、快速开始

```bash
cd <path-to>/agent_scope

# 虚拟环境由 uv 创建（仓库根的 .venv）
uv venv .venv
uv pip install --python .venv/bin/python \
    agentscope httpx aiosmtplib aioimaplib beautifulsoup4 \
    asyncpg aiomysql pymongo sqlglot

# 运行（从仓库根；不要用 scope/../.venv/bin/python 这种相对路径，
# uv 会因 sys.prefix 解析不一致打印 RuntimeWarning）
uv run --no-project python your_script.py
```

也可以直接使用绝对路径解释器：

```bash
/mnt/sda2/qoder/qoder/agent_scope/.venv/bin/python your_script.py
```

工具层要求 `scope/` 在 `sys.path`（当前工具文件使用顶层 `from config import ...`）：

```python
import asyncio
import sys

sys.path.insert(0, "<path-to>/agent_scope/scope")

import config
from tools.db.main_db import async_db_tools


async def main():
    await config.aload()   # 可选：装配期预载 config.db；不调用会在首次 get 时惰性建库

    r = await async_db_tools({
        "function": "run_query",
        "db_config": {
            "db_type": "sqlite",
            "path": "/path/to/demo.db",
            "database": "demo",
        },
        "sql": "SELECT 1",
    })
    print(r["code"], r["message"], r["data"])


asyncio.run(main())
```

返回统一信封：

```python
{"code": 200 | 400 | 500, "data": ..., "message": "..."}
```

### 后端统一入口

业务后端只需要调用 `scope/main.py`：

```python
from scope.main import async_dispatch

r = await async_dispatch({
    "domain": "rag",
    "action": "tools",
    "data": {
        "function": "read",
        "rag_config": {"type": "zvec", "zvec_config": {...}},
        "search_config": {"query": "如何部署", "top_k": 5},
    },
})
```

```python
r = await async_dispatch({
    "domain": "agent",
    "action": "create",
    "data": {
        "agent": {"name": "assistant", "system_prompt": "..."},
        "llm": {...},
    },
})
```

支持 domain：

```text
tool / rag / llm / media / agent / permission / middleware
workspace / realtime / config / system
```

注意：

- dispatch 返回统一信封
- `agent/model/workspace/middleware` 创建结果是进程内对象
- 如果走 HTTP，需要上层加 session registry，把对象换成 ID
- HTTP/SSE 服务入口尚未实现；当前 `create_app` 也还没加

注意：

- 业务参数平铺在 `data` 顶层，不嵌进 `arguments`。
- 经 AgentScope `FunctionTool` 调用时需要包一层 `{"data": {...}}`。
- 写操作使用独立入口 `async_db_write_tools`。

---

## 四、下一步路线

| 优先级 | 内容 |
|---|---|
| P0 | 框架骨架：`agent/builder.py`、`agent/runtime.py`、`agent/context.py`、Toolkit 装配、skills、`main.py`、`pyproject.toml` |
| P1 | `permission/`：已实现 PermissionContext、SQLite 规则/审计/pending、函数级工具适配；剩余前端审批 UI 与 Redis/Postgres pending |
| P1 | `rag/`：官方 `KnowledgeBase` + `RAGMiddleware`，文件解析/切片/embedding/注册表，多租户隔离 |
| P2 | 子智能体与委派、A2A、Mem0/文件记忆、storage、agentscope.app 服务化 |
| P3 | 钉钉工具、多模态（视频/TTS/STT）、多向量库后端 |

实施顺序与验收标准见 [docs/框架层规划.md](scope/docs/框架层规划.md)。

---

## 五、验证状态

已执行：

- `compileall` 全量编译通过；
- 5 个工具域入口与 12 个核心模块 import 通过；
- 7 个工具入口 × 8 种坏入参（`None` / `str` / `list` / `int` / 空 function / 非字符串 / 未知 function）
  无崩溃，均返回统一信封；
- 每个 function 空参数调用均返回 400，无异常；
- SQLite 实际查询、A17 转义、C2 白名单、`_fs` 读写闸门均已冒烟验证。

目前还没有正式测试目录；P0 阶段会补工具契约、审批状态机、RAG 租户隔离三组测试。

---

## 六、安全约定

- 任何真实 API Key、邮箱授权码、数据库密码都不进代码、不进 Git。
- 敏感配置写入 `scope/config/config.db`（已在 `.gitignore`）。
- `scope/tools/mcp/mcp_servers.json` 可能含 token，不入库；模板见 `mcp_servers.example.json`。
- 提交前建议执行：

```bash
git status
git diff --cached
```

确认没有 `.env`、`config.db`、`mcp_servers.json`、日志或密钥。

---

## 七、文档

先从 [scope/docs/README.md](scope/docs/README.md) 开始，按用途查，不必通读。

---

## 八、发布到 GitHub（维护者）

GitHub 已不支持用账户密码做 Git 认证，请使用 **PAT（Personal Access Token）** 或 **SSH Key**。
不要把 GitHub 密码、PAT 写进代码、README 或命令历史。

### 方式 A：SSH Key（推荐）

```bash
# 1. 生成密钥（已有可跳过）
ssh-keygen -t ed25519 -C "your-email@example.com"

# 2. 把 ~/.ssh/id_ed25519.pub 的内容添加到 GitHub → Settings → SSH and GPG keys

# 3. 在 GitHub 网页创建空仓库（不要勾选 README / .gitignore / License）

# 4. 添加远端并推送（远端名用 github，避免覆盖已有 origin）
git remote add github git@github.com:<your-name>/agent-scope.git
git branch -M main
git push -u github main
```

### 方式 B：HTTPS + PAT

```bash
# GitHub → Settings → Developer settings → Personal access tokens
# 创建 fine-grained token，至少授予目标仓库 Contents: Read and write

git remote add github https://github.com/<your-name>/agent-scope.git
git push -u github main
# 用户名填 GitHub 用户名，密码填 PAT（不是账户密码）
```

推荐用 `gh auth login` 或系统凭据管理器保存 PAT，不要用
`git config credential.helper store` 明文落盘。

> 当前仓库的 `origin` 指向本地 Gitea，不要直接覆盖；新增 `github` 远端即可同时保留两边。


---

## 九、平台前后端（v0.3.0）

在框架层之上新增了一套精简的业务平台，当前只做基础账号与权限配置：

- 登录 / 注册 / JWT 鉴权、头像 URL
- 用户管理（角色、直属上级、启停、重置密码）
- 默认设置（站点、账号、安全、界面共 15 项，可恢复默认）
- 权限分级：角色权限 → 超管单独授权 → 上级/本人逐级收缩 → 超管临时越级授权
- 运行状态：CPU / 内存 / 磁盘 / GPU / 网络与 IP / Redis / PostgreSQL
- Redis 滑动窗口限流，不可用时自动降级进程内
- 菜单可配置：两级分组、分组折叠、用户自定义顺序/隐藏、自定义图标/排序/权限点
- 系统 / 默认配置独立菜单：用户管理、运行信息、系统设置、角色权限、菜单配置、Agent 配置
- 普通用户 / 上级 / 超管三种菜单视角，超管额外「管理后台」入口
- AI/Scope 与系统配置分离：Agent 配置页支持对话模型、Embedding、厂商预设与在线获取模型
- AI 工具权限：默认全部工具，可单独授权，上级可逐级收窄
- AI 安全默认值：安全提示词、身份锁定、数据库库/表白黑名单、写权限开关
- AI 对话：会话持久化、SSE 流式、按用户工具权限装配 Agent
- 用户级 Agent 配置：跟随系统默认或自定义模型/Key/提示词
- 用户级工具配置：邮箱 / 数据库连接，可使用系统默认或自定义
- 工具审批、模型统计（按天/模型/用户）、会话重命名
- 邮箱默认配置，敏感项脱敏；默认角色含 `ai.use` 权限
- 邮件发送工具（SMTP 默认配置 + 测试接口）
- 侧栏可收缩、移动端适配界面

```text
agent_scope/
├── backend/          # FastAPI + SQLAlchemy async + PostgreSQL
│   ├── app/          # api / services / models / security / seed
│   ├── .env.example  # 数据库、JWT、端口等启动参数
│   └── doc/          # 开发记录、接口说明、数据库说明
└── frontend/         # Vue 3 + Vite + Element Plus
    ├── src/          # views / router / stores / utils / styles
    ├── .env.example  # 端口、代理目标、API 前缀
    └── doc/          # 开发记录、页面说明
```

启动：

```bash
# 后端
uv pip install --python .venv/bin/python -r backend/requirements.txt
cd backend && cp .env.example .env && ../.venv/bin/python run.py

# 前端（另开终端）
cd frontend && cp .env.example .env && npm install && npm run dev
```

默认数据库 `agent_scope`，首次启动自动写入内置账号：

| 账号 | 密码 | 角色 |
|---|---|---|
| `MX` | `990108` | 超级管理员 |
| `张三` | `990108` | 管理员（领导） |
| `李四` | `990108` | 普通用户（上级：张三） |

文档导航：

| 端 | 文档 |
|---|---|
| 后端 | [README](backend/doc/README.md) / [接口说明](backend/doc/接口说明.md) / [参数说明](backend/doc/参数说明.md) / [CODE_INDEX](backend/doc/CODE_INDEX.md) / [配置说明](backend/doc/配置说明.md) / [数据库说明](backend/doc/数据库说明.md) / [踩坑记录](backend/doc/踩坑记录.md) / [开发记录](backend/doc/开发记录.md) |
| 前端 | [README](frontend/doc/README.md) / [页面说明](frontend/doc/页面说明.md) / [CODE_INDEX](frontend/doc/CODE_INDEX.md) / [配置说明](frontend/doc/配置说明.md) / [踩坑记录](frontend/doc/踩坑记录.md) / [开发记录](frontend/doc/开发记录.md) |
