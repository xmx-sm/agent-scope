# frontend CODE_INDEX

前端文件级索引。找组件、改页面、加路由前先在此定位。

- 源码规模：`src/` 下 **约 2900 行 / 16 个文件**
- 分层：入口 → 路由/状态/请求 → 页面组件
- 行数以 `wc -l` 为准

---

## 一、入口与基础设施

| 文件 | 行数 | 职责 | 依赖 |
|---|---:|---|---|
| `src/main.js` | 21 | 创建 App，挂载 Pinia、Router、Element Plus、图标 | `App.vue`、`router`、`styles` |
| `src/App.vue` | 3 | 仅 `<router-view />` | — |
| `src/router/index.js` | 94 | 路由表、登录守卫、权限守卫 | `stores/auth`、全部页面 |
| `src/stores/auth.js` | 88 | token/user/permissions 持久化、登录/注册/刷新/登出 | `utils/api` |
| `src/utils/api.js` | 45 | Axios 实例、Token 注入、统一解包、401 清理 | `element-plus` |
| `src/styles/main.css` | 186 | 全局变量、面板、移动端断点、登录页样式 | — |
| `index.html` | — | viewport、`viewport-fit=cover`、主题色 | — |
| `vite.config.js` | — | 端口、代理、`loadEnv` | — |

### 请求链路

```text
页面组件
  → utils/api.js（注入 Bearer、解包、401 跳登录）
    → /api（Vite 代理）
      → 后端 routers/*
```

### 登录态链路

```text
Login.vue → auth.login()
  → POST /auth/login
  → 保存 access_token / refresh_token / user
  → GET /auth/me 刷新 permissions
  → router.replace(redirect || /dashboard)
```

---

## 二、路由与页面

| 路径 | 组件 | 行数 | 权限 | 说明 |
|---|---|---:|---|---|
| `/login` | `views/Login.vue` | 107 | 公开 | 登录、站点信息、已登录回跳 |
| `/register` | `views/Register.vue` | 112 | 公开 | 注册、确认密码 |
| `/dashboard` | `views/Dashboard.vue` | 216 | `dashboard` | 统计、快捷入口、我的权限 |
| `/permissions` | `views/MyPermissions.vue` | 173 | `permissions.self` | 有效权限、临时授权、自我收缩 |
| `/team/permissions` | `views/TeamPermissions.vue` | 191 | `permissions.team` | 下属列表与收缩 |
| `/system/status` | `views/SystemStatus.vue` | 408 | `system.status` | CPU/GPU/磁盘/Redis 等 |
| `/profile` | `views/Profile.vue` | 166 | `profile` | 资料、头像、改密 |
| `/admin/users` | `views/admin/UserManage.vue` | 632 | `admin.users` + 超管 | 用户 CRUD、权限弹窗 |
| `/admin/config/system` | `views/admin/ConfigurationSystem.vue` | 200 | `admin.settings` + 超管 | 系统设置 |
| `/admin/config/roles` | `views/admin/ConfigurationRoles.vue` | 130 | `admin.permissions` + 超管 | 角色权限 |
| `/admin/config/menus` | `views/admin/ConfigurationMenus.vue` | 14 | `admin.menus` + 超管 | 菜单配置 |
| `/admin/agent` | `views/admin/AgentConfig.vue` | 340 | `ai.config` + 超管 | Agent 配置 |
| `/` | `views/Layout.vue` | 359 | 登录 | 侧栏、抽屉、顶栏、用户菜单 |

### 路由守卫顺序

1. 公开页：已登录 → `/dashboard`
2. 未登录 → `/login?redirect=...`
3. 内存无 user → `fetchMe()`，失败清登录态
4. `superAdminOnly` 页面 → 非超管回 `/dashboard`
5. `meta.permission` 不在有效权限内 → `/dashboard`

---

## 三、页面职责

### Layout.vue

- 桌面固定侧栏，可收缩（224px ↔ 68px），状态存 `localStorage.sidebar_collapsed`
- 移动端（<768px）改为左侧抽屉
- 菜单按 `permissions` 过滤；`superAdmin` 项再做角色判断
- 顶栏头像、个人中心/我的权限/退出登录

### Login / Register

- 读 `/public/site` 展示站点名与注册开关
- 表单校验：账号必填、密码 ≥6、确认密码一致
- 成功后直接拉 `/auth/me`

### Dashboard

- 角色问候、统计卡片（超管）
- 快捷入口按有效权限过滤
- 权限标签展示

### Profile

- 昵称/邮箱/手机号/头像 URL
- 头像实时预览；保存后 `fetchMe()` 同步顶栏
- 改密成功清登录态回登录页

### UserManage（超管）

- 搜索、角色筛选、分页
- 桌面表格 / 移动卡片
- 新增、编辑、删除、重置密码
- 权限弹窗：单独授权、收缩、临时越级授权

### Settings（超管）

- 默认设置按「站点/账号/安全/界面」分组
- 逐项保存、恢复默认
- 角色权限矩阵，`super_admin` 只读全选

### MyPermissions / TeamPermissions

- 展示有效权限、收缩记录、临时授权与到期时间
- 自我收缩 / 收缩下属；保存后刷新 `/auth/me`
- 临时授权不能收缩

### SystemStatus

- 10 秒自动刷新（可关）
- CPU、内存、磁盘、GPU、网络、进程、Redis、PostgreSQL
- 移动端双列 → 单列自适应

---

## 四、依赖方向

```text
views/* ──► stores/auth ──► utils/api
   │            │
   └────────────┴────────► vue-router
   └─────────────────────► element-plus / icons
```

禁止：

- `utils/api` 导入 `stores`（会成环）
- 页面直接 `fetch` 调用后端（统一走 api.js）
- 页面自行解析 `code`（拦截器已解包）

---

## 五、新增页面步骤

1. `src/views/Xxx.vue` 新建页面。
2. `router/index.js` 注册路由，设置 `meta.title` / `meta.permission` / `meta.superAdminOnly`。
3. `Layout.vue` 的 `allMenus` 增加菜单项。
4. 若权限点新增，先在后端 `core/permissions.py` 登记并在矩阵/角色默认值中配置。
5. 同步《页面说明.md》《CODE_INDEX.md》《开发记录.md》。

---

## 六、构建产物

```text
dist/
├── index.html
└── assets/*.js / *.css
```

Vite 会按路由做动态 import，页面级 chunk 分离；Element Plus 主包仍较大（gzip 约 416KB），属于当前已知优化项。

---

## 七、v0.3.0 新增（历史，部分文件已被 v0.4.1 拆分）

| 文件 | 行数 | 职责 |
|---|---:|---|
| `src/components/MenuConfig.vue` | 310 | 菜单配置表格、新增/编辑弹窗、图标选择、上移/下移 |
| `src/views/Layout.vue` | 380 | 改为从 `/menus/mine` 动态渲染两级菜单 |
| `src/views/admin/Settings.vue` | 317 | 新增「菜单配置」Tab；配置支持 float 与 secret |
| `src/stores/auth.js` | 100 | 新增 `menus` 状态与 `fetchMenus()` |

### 动态菜单依赖

```text
Login/fetchMe → GET /menus/mine → auth.menus
Layout → auth.menus（两级渲染）
Settings → MenuConfig → /admin/menus CRUD + reorder + /admin/permissions
```

### 菜单配置字段

`key / parent_key / title / path / icon / permission / super_only / sort_order / is_visible`

---

## 八、v0.3.2 新增（历史，AdminHome 已在 v0.4.1 移除）

| 文件 | 行数 | 职责 |
|---|---:|---|
| `src/views/AdminHome.vue` | 129 | 超管管理后台聚合入口 |
| `src/views/MenuPersonalize.vue` | 225 | 用户菜单排序与隐藏 |
| `src/views/Layout.vue` | 410 | 分组折叠、动态菜单、菜单个性化入口 |
| `src/views/admin/Settings.vue` | 350 | 配置分组折叠、菜单配置 Tab |

### 新路由

| 路径 | 页面 | 权限 |
|---|---|---|
| `/admin` | AdminHome | `admin.users` + 超管 |
| `/menu-settings` | MenuPersonalize | `dashboard` |

### 用户偏好链路

```text
MenuPersonalize → GET /menus/catalog + GET /menus/prefs
                → PUT /menus/prefs
                → auth.fetchMenus() → Layout 立即更新
```

---

## 九、v0.4.0 新增

| 文件 | 行数 | 职责 |
|---|---:|---|
| `src/views/admin/AgentConfig.vue` | 340 | Agent 配置页，对话/向量/Scope 三 Tab，厂商选择与获取模型 |
| `src/views/admin/Settings.vue` | 350 | 只加载 `domain=system` 配置 |
| `src/views/AdminHome.vue` | 130 | 新增 Agent 配置入口卡片 |

### 依赖

```text
AgentConfig → GET /admin/configs?domain=agent
            → GET /admin/agent/providers
            → POST /admin/agent/models
            → PUT /admin/configs/{key}
```

---

## 十、v0.4.1 配置页拆分

| 文件 | 行数 | 路由 | 职责 |
|---|---:|---|---|
| `src/views/admin/ConfigurationSystem.vue` | 200 | `/admin/config/system` | 系统域配置折叠列表 |
| `src/views/admin/ConfigurationRoles.vue` | 130 | `/admin/config/roles` | 角色权限矩阵 |
| `src/views/admin/ConfigurationMenus.vue` | 14 | `/admin/config/menus` | 菜单配置容器 |
| `src/views/admin/AgentConfig.vue` | 340 | `/admin/agent` | Agent 模型配置 |

已删除：

- `src/views/admin/Settings.vue`（左右 Tab）
- `src/views/AdminHome.vue`（聚合入口）

---

## 十一、v0.5.0 AI 工具权限

| 文件 | 行数 | 职责 |
|---|---:|---|
| `src/views/admin/UserManage.vue` | 808 | 权限弹窗改为 AI 工具模式/清单 |
| `src/views/TeamPermissions.vue` | 225 | 上级收窄下属 AI 工具 |
| `src/views/MyPermissions.vue` | 261 | 展示并自关闭 AI 工具 |

接口：`/tools/mine`、`/tools/team`、`/admin/users/{id}/tools`。
