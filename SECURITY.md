# Security Policy

## 支持范围

当前维护版本：`v0.25.x`

## 联系方式

一般问题请联系：mingxin0108@139.com

## 报告安全问题

请优先使用 GitHub 的 **Private vulnerability reporting / Security advisory**，不要在公开 Issue 中粘贴：

- 真实 API Key
- 数据库密码
- 邮箱授权码
- JWT Secret
- 可复现的越权请求与完整用户数据

如果仓库未开启私密报告，请先通过仓库所有者公开资料中的私下联系方式联系。

## 公开仓库 / 部署前检查

1. 修改 `JWT_SECRET` 为随机长字符串。
2. 修改 PostgreSQL / Redis 默认密码。
3. 修改种子账号密码 `990108`。
4. 配置真实模型 / Embedding / 工具凭证时只写入运行数据库或本地 `.env`。
5. 确认以下内容未入库：

```text
.env
config.db
mcp_servers.json
backend/uploads/
logs/
node_modules/
dist/
```

6. 执行：

```bash
git ls-files | grep -E '(^|/)(\.env|config\.db|mcp_servers\.json|uploads/|logs?/|node_modules/|dist/)'
git grep -nIE 'sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY'
```

## 安全边界

本项目提供 IAM 分级、AI 工具权限、输入防注入、输出脱敏、数据库安全策略与服务端身份锁定，但不等同于完整零信任或等保方案。

生产部署仍应补充：

- 网络隔离与反向代理
- HTTPS
- 密钥托管
- 审计日志留存
- 备份与恢复
- 依赖漏洞扫描
- 定期渗透测试与权限复核
