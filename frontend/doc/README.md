# frontend/docs

前端配套文档。按用途查。

| 文档 | 什么时候读 | 内容 |
|---|---|---|
| [页面说明.md](./页面说明.md) | 改页面前 | 路由、页面功能、权限控制、移动端适配 |
| [CODE_INDEX.md](./CODE_INDEX.md) | 找文件 / 改组件前 | 文件行数、组件职责、路由映射、依赖方向 |
| [配置说明.md](./配置说明.md) | 启动 / 调整界面行为前 | `.env` 变量、后端运行配置、断点与刷新策略 |
| [踩坑记录.md](./踩坑记录.md) | 报错时 / 改交互前 | 本项目实际踩过的坑与处理 |
| [开发记录.md](./开发记录.md) | 了解进度 | 版本进度、设计决策、已知限制 |

## 三十秒上手

```bash
cd frontend
cp .env.example .env
npm install
npm run dev      # http://127.0.0.1:5182
npm run build    # dist/
```

开发代理：`/api` → `VITE_PROXY_TARGET`（默认 `http://127.0.0.1:8000`）。

## 关键约定

1. **Axios 统一解包**：拦截器返回 `data`，业务代码不再判断 `code`。
2. **登录态存 Pinia + localStorage**：`access_token`、`user`、`permissions`。
3. **菜单/路由由权限驱动**：`/auth/me` 返回的 `permissions` 是唯一来源。
4. **移动端断点 767px**：桌面侧栏 / 移动抽屉、表格 / 卡片双视图。
5. **新增页面三步**：`views/` 组件 → `router/index.js` → `Layout.vue` 菜单项。

## 技术栈

- Vue 3（`<script setup>`）
- Vite 5
- Element Plus + `@element-plus/icons-vue`
- Pinia
- Axios
- Vue Router

## 目录

```text
frontend/
├── .env.example
├── index.html
├── vite.config.js
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router/index.js      # 路由与权限守卫
│   ├── stores/auth.js       # 登录态与权限
│   ├── utils/api.js         # Axios 封装
│   ├── styles/main.css      # 全局样式与移动端断点
│   └── views/               # 页面
└── doc/
```

文件级索引见 [CODE_INDEX.md](./CODE_INDEX.md)。
