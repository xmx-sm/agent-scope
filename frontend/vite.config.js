import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // 子路径部署：与 Nginx 的 location /agent_scope/ 保持一致
  const base = env.VITE_BASE || '/agent_scope/'
  // 浏览器请求前缀；生产由 Nginx 转发到后端，开发由 Vite 代理转发
  const apiBase = env.VITE_API_BASE || `${base.replace(/\/$/, '')}/api`
  const proxy = {}

  if (!/^https?:\/\//i.test(apiBase)) {
    proxy[apiBase] = {
      target: env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(apiBase, '/api')
    }
  }

  return {
    base,
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: Number(env.VITE_PORT || 5182),
      proxy
    }
  }
})
