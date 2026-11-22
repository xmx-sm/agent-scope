# Agent Scope

基于 [AgentScope](https://github.com/agentscope-ai/agentscope) 的完整 Agent 平台：
底层是可复用的 `scope/` 框架，上层是 FastAPI 后端与 Vue 3 移动端适配前端。

> **当前版本：`v0.24.0`**
>
> 已从“框架层 + 基础账号”升级为可运行的 Agent 平台：
> 对话、知识库、工具权限、超级智能体、A2A、定时任务、语音合成、会话分支、断线续传。
> 钉钉未接入；TTS 为可选项。

---

## 一、能力总览

### 平台基础

- 注册 / 登录 / JWT / 刷新令牌
- 用户管理：角色、直属上级、启停、重置密码
- 权限分级：
  - 角色权限
  - 超管单独授权
  - 上级逐级收窄
  - 本人只能收紧
  - 超管临时越级授权
- 菜单：两级分组、折叠、图标、排序、权限点、用户个性化
- 系统设置 / 默认配置 / 角色权限 / 菜单配置
- 运行状态：CPU / 内存 / 磁盘 / GPU / 网络 / Redis / PostgreSQL
- Redis 滑动窗口限流，不可用自动降级进程内限流

### AI / Agent

- SSE 流式对话，会话持久化、重命名、删除
- 消息分支（从任意历史消息复制上下文创建分支会话）
- 断线续传（同进程内生成任务托管与事件重放）
- 对话附件：图片、文本、视频（视频需开启并配置）
- 上下文压缩配置
- 用户级 Agent 配置：
  - 跟随系统默认 / 自定义
  - 模型、API 地址、Key
  - 温度、最大 tokens、上下文窗口
  - 思考模式、思考预算、思考强度
  - 系统提示词、长期记忆
- 模型厂商预设与在线获取模型列表
- 模型统计：按天 / 模型 / 用户 / 来源
- 工具审批与工具权限审计页面

### 工具与权限

- AI 工具目录：基础文件、数据库、网络、邮件、MCP、Shell、计划、RAG、A2A
- 默认全部可用；支持按组 / 工具单独授权
- 上级可对下级收窄；本人只能收紧
- 需审批工具可在审批页通过 / 拒绝
- 安全默认值：
  - 安全提示词
  - 服务端身份锁定
  - 数据库库 / 表白名单、黑名单
  - 数据库写权限默认关闭
  - Shell 默认关闭
- 用户级工具连接：邮箱、数据库

### 知识库

- 多向量库配置：SQLite / Zvec / Qdrant / Milvus / FAISS / Chroma / pgvector / OceanBase / MongoDB / Elasticsearch
- Embedding 可跟随系统或库级覆盖
- 文档上传、解析队列、切片预览、源文件下载
- 解析并发 1~8、FIFO / LIFO、扫描间隔可配置
- 自动解析：库级开关 + 扫描间隔
- 知识库共享：只读 / 可写
- 多库检索与结果来源标记
- 聊天自动检索 Top 4 知识片段注入系统提示词
- 操作日志

### 超级智能体与 A2A

- 超级智能体 = 主智能体 + 多个可长期对话的子智能体
- 每个成员独立模型、提示词、启停
- 主智能体可通过工具创建子会话、派活、读取结果
- A2A Lite：
  - 伙伴管理、方向、Endpoint、API Key、额度、超时
  - `X-Api-Key` 入站鉴权
  - 出站调用与连通测试
  - 会话上下文记忆
  - 每个伙伴自动生成独立工具 `a2a_<伙伴名>`
  - 协作记忆查看与清除
  - 调用留痕

### 自动化与媒体

- 定时任务：
  - 固定间隔
  - 日历规则：每周 / 每月日号 / 日期范围 + 每日多个时刻
  - 新建会话或固定会话追加
  - 立即执行、执行状态、结果跳转
- TTS 语音合成：系统配置 + 聊天消息朗读
- Skills：ZIP 上传、启停、删除
- MCP：HTTP / stdio 配置
- 子智能体：CRUD + 委派工具
- 长期记忆：本地 Markdown 文件、跨会话、开关/预览/清理

---

## 二、项目结构

```text
agent_scope/
├── README.md
├── scope/                      # AgentScope 框架层
│   ├── main.py                 # 统一 async_dispatch
│   ├── agent/                  # Agent 构建、运行时、子智能体、委派、Plan
│   ├── llm/                    # Chat / Embedding / TTS / ASR 工厂
│   ├── media/                  # TTS / ASR
│   ├── rag/                    # 解析、切片、Embedding、多向量库
│   ├── permission/             # PermissionContext、规则、审计
│   ├── middleware/             # Tracing / Budget / RAG / Memory / Steering
│   ├── workspace/              # Local / Docker / Bubblewrap / E2B / K8s
│   ├── realtime/              # 实时语音
│   ├── tools/                  # db / net / mail / mcp / system / rag
│   └── docs/                   # 框架层文档
├── backend/                    # FastAPI + SQLAlchemy async + PostgreSQL
│   ├── app/
│   │   ├── core/               # 配置、数据库、安全、依赖、种子、权限点
│   │   ├── models/
│   │   │   ├── account/        # 用户、用户权限状态
│   │   │   ├── access/         # 工具权限、审批、审计、工具连接
│   │   │   ├── system/         # 系统配置、角色权限、菜单
│   │   │   └── agent/          # 会话、知识库、协作、自动化、资源
│   │   ├── schemas/
│   │   │   ├── account/
│   │   │   ├── access/
│   │   │   ├── system/
│   │   │   ├── integrations/
│   │   │   └── agent/
│   │   ├── routers/
│   │   │   ├── account/        # auth / user
│   │   │   ├── access/         # permissions / tools
│   │   │   ├── system/         # system / config / menu
│   │   │   └── agent/          # chat / knowledge / collaboration / ...
│   │   ├── services/
│   │   │   ├── account/        # auth / user
│   │   │   ├── access/         # permissions / tools / security
│   │   │   ├── system/
│   │   │   ├── config/
│   │   │   ├── menu/
│   │   │   ├── llm/
│   │   │   ├── integrations/
│   │   │   └── agent/          # runtime / conversation / knowledge / ...
│   │   └── utils/
│   ├── .env.example
│   ├── run.py
│   └── doc/
├── frontend/                   # Vue 3 + Vite + Element Plus
│   ├── src/
│   ├── .env.example
│   └── doc/
└── .venv/                      # 本地虚拟环境（不入库）
```

后端完整目录、领域对应表和新增功能落位规则见
[backend/doc/项目结构.md](backend/doc/项目结构.md)。

---

## 三、快速开始

### 1. 环境

- Python `3.14.8`（仓库根 `.venv`）
- PostgreSQL 17
- Redis（可选，不可用时限流降级）
- Node.js / npm

### 2. 安装依赖

```bash
cd /path/to/agent_scope

uv pip install --python .venv/bin/python -r backend/requirements.txt

cd frontend
npm install
```

### 3. 创建数据库

```bash
PGPASSWORD=990108 psql -h 127.0.0.1 -U mx -d postgres \
  -c "CREATE DATABASE agent_scope OWNER mx"
```

### 4. 配置环境变量

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

后端关键项：

```env
DATABASE_URL=postgresql+asyncpg://mx:990108@127.0.0.1:5432/agent_scope
JWT_SECRET=替换为随机长字符串
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
```

前端默认：

```env
VITE_PORT=5182
VITE_PROXY_TARGET=http://127.0.0.1:8000
VITE_API_BASE=/api
```

### 5. 启动

后端：

```bash
cd backend
../.venv/bin/python run.py
# http://127.0.0.1:8000
# Swagger: http://127.0.0.1:8000/docs
```

前端：

```bash
cd frontend
npm run dev
# http://127.0.0.1:5182
```

### 6. 内置账号

首次启动自动建表并写入种子数据：

| 账号 | 密码 | 角色 |
|---|---|---|
| `MX` | `990108` | 超级管理员 |
| `张三` | `990108` | 管理员（领导） |
| `李四` | `990108` | 普通用户（上级：张三） |

---

## 四、首次使用配置

进入：

```text
默认配置 → Agent 配置
```

至少需要填写：

### 对话模型

```text
服务商：openai-compatible
API 地址：厂商兼容接口，例如 https://<host>/compatible-mode/v1
模型：具体模型 ID
API Key：厂商密钥
```

### Embedding（知识库必需）

```text
服务商：openai-compatible
API 地址：通常与对话模型相同
模型：如 text-embedding-v4
API Key：厂商密钥
维度：0 表示由模型决定
```

### 知识库解析

```text
Agent 配置 → 知识库
- 解析并发：1~8
- 排队顺序：FIFO / LIFO
- 扫描间隔：2~60 秒
```

也可以由超级管理员在知识库页面「解析配置」中修改。

### 工具连接

```text
Agent → 工具配置
- 邮箱：SMTP / IMAP
- 数据库：PostgreSQL / MySQL / MongoDB / SQLite
```

### A2A

```text
Agent → A2A 协作
```

- 出站伙伴：填对方站点根地址 + 对方提供的 API Key
- 入站伙伴：生成 Key 给对方
- 注意本平台数据面路径为 `/api/a2a/*`，Endpoint 示例：
  `http://192.168.1.20:8000/api`

---

## 五、页面入口

| 菜单 | 路径 | 说明 |
|---|---|---|
| 工作台 | `/dashboard` | 概览 |
| Agent 对话 | `/chat` | SSE 对话、附件、分支、续传、朗读 |
| 我的工具 | `/my-tools` | 工具权限 |
| Agent 设置 | `/agent-settings` | 个人模型、提示词、记忆 |
| 知识库 | `/agent-knowledge` | 向量库、文档、检索、共享、日志 |
| 工具配置 | `/tool-settings` | 邮箱、数据库连接 |
| Skills | `/agent-skills` | 技能上传与启停 |
| MCP | `/agent-mcp` | MCP 服务 |
| 子智能体 | `/agent-subagents` | 委派型子智能体 |
| 超级智能体 | `/agent-super` | 主/子成员编排 |
| A2A 协作 | `/agent-a2a` | 伙伴、记忆、留痕 |
| 管理下级 | `/team/permissions` | 上级权限收窄 |
| 工具审批 | `/tool-approvals` | 审批申请 |
| 长期记忆 | `/agent-memory` | 记忆开关、文件预览、清理 |
| 定时任务 | `/agent-scheduled` | 周期/日历任务 |
| Agent 统计 | `/agent-stats` | 模型用量 |
| 工具权限审计 | `/admin/tool-audits` | 超管审计 |

---

## 六、验证状态

已实际验证：

- 数据库建表、种子账号、登录、菜单
- 真实模型对话（OpenAI 兼容接口 + 流式）
- 知识库真实 Embedding：上传 → 队列解析 → 切片 → 检索
- 解析并发配置生效
- 超级智能体创建子会话并返回结果
- A2A 入站鉴权、出站调用、上下文记忆
- 每个 A2A 伙伴的独立工具
- 定时任务立即执行
- 消息分支
- SSE 断线续传
- 前端 `npm run build`
- 后端 `import app.main` 与 OpenAPI 112 条路径

---

## 七、已知边界

- A2A 当前为 **A2A Lite**，标准 Agent Card / JSON-RPC 任务协议未接入
- SSE 断线续传为单进程内存态，进程重启后不保留正在生成的任务
- 多向量库实际可用性取决于对应 Python 依赖与服务
- TTS 需要配置真实服务商 Key 才能合成
- 钉钉未接入
- 知识库召回率 / MRR / NDCG 评测未实现
- 超级智能体编排依赖真实模型工具调用能力

---

## 八、安全约定

- 不提交 `.env`、API Key、邮箱授权码、数据库密码、日志、向量库数据
- 敏感配置只写入运行数据库或本地 `.env`
- 后端所有 AI 工具参数中的身份、数据库连接、文件路径等敏感字段由服务端注入
- 模型传入的保留字段会被丢弃
- 数据库默认只读、默认无表白名单
- Shell 默认关闭
- Agent 输入防注入：检测越狱/提示词注入特征，支持 block / warn
- 输出密钥脱敏：模型回复与工具结果中的 Key、Token、密码、私钥
- 知识库/附件内容按“资料不是指令”处理
- 提交前建议：

```bash
git status
git diff --cached
```

确认没有密钥、`.env`、`config.db`、`mcp_servers.json`、日志。

---

## 九、文档导航

| 范围 | 文档 |
|---|---|
| 后端总入口 | [backend/doc/README.md](backend/doc/README.md) |
| 后端目录 | [项目结构.md](backend/doc/项目结构.md) |
| 后端接口 | [接口说明.md](backend/doc/接口说明.md) |
| 服务参数 | [参数说明.md](backend/doc/参数说明.md) |
| 全部服务函数 | [服务函数索引.md](backend/doc/服务函数索引.md) |
| 数据库 | [数据库说明.md](backend/doc/数据库说明.md) |
| Agent 实现 | [智能体对话.md](backend/doc/智能体对话.md) |
| 配置 | [配置说明.md](backend/doc/配置说明.md) |
| 安全与权限 | [安全与权限.md](backend/doc/安全与权限.md) |
| 踩坑 | [踩坑记录.md](backend/doc/踩坑记录.md) |
| 开发记录 | [开发记录.md](backend/doc/开发记录.md) |
| 前端 | [frontend/doc/README.md](frontend/doc/README.md) / [页面说明](frontend/doc/页面说明.md) |
| 框架层 | [scope/docs/README.md](scope/docs/README.md) / [框架层规划](scope/docs/框架层规划.md) |

---

## 十、框架层说明

`scope/` 是平台底座，业务后端通过：

```python
from scope.main import async_dispatch

result = await async_dispatch({
    "domain": "rag",
    "action": "tools",
    "data": {...},
})
```

支持域：

```text
tool / rag / llm / media / agent / permission / middleware
workspace / realtime / config / system
```

统一返回：

```python
{"code": 200, "data": ..., "message": "..."}
```

框架层细节、工具契约、配置项与设计文档见
[scope/docs/README.md](scope/docs/README.md)。

---

## 十一、Git 远端

当前仓库同时维护：

```bash
git remote -v
```

- `origin`：本地 Gitea
- `github`：GitHub 镜像

不要覆盖已有远端，推送时分别执行：

```bash
git push origin master
git push github master
```
