# 前端文档

Vue 3 + Vite + Element Plus 移动端适配界面。

| 文档 | 内容 |
|---|---|
| [开发记录.md](./开发记录.md) | 进度、页面设计、已知问题 |
| [页面说明.md](./页面说明.md) | 路由、页面功能、权限控制、移动端适配 |

## 技术栈

- Vue 3（`<script setup>`）
- Vite 5
- Element Plus + `@element-plus/icons-vue`
- Pinia（登录态）
- Axios（统一响应/401 处理）
- Vue Router（登录与权限守卫）

## 本地启动

```bash
cd frontend
cp .env.example .env
npm install
npm run dev      # http://127.0.0.1:5173
npm run build    # 产物在 dist/
```

开发代理：`/api` → `VITE_PROXY_TARGET`（默认 `http://127.0.0.1:8000`）。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| VITE_APP_TITLE | Agent Scope Platform | 顶栏标题 |
| VITE_PORT | 5173 | 开发端口 |
| VITE_PROXY_TARGET | http://127.0.0.1:8000 | 后端地址 |
| VITE_API_BASE | /api | 浏览器请求前缀 |

## 目录

```text
frontend/
├── .env.example
├── index.html
├── vite.config.js
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router/index.js      # 路由与守卫
│   ├── stores/auth.js       # 登录态与权限
│   ├── utils/api.js         # Axios 封装
│   ├── styles/main.css      # 全局样式与移动端断点
│   └── views/
│       ├── Login.vue
│       ├── Register.vue
│       ├── Layout.vue
│       ├── Dashboard.vue
│       ├── Profile.vue
│       └── admin/
│           ├── UserManage.vue
│           └── Settings.vue
└── doc/
```
