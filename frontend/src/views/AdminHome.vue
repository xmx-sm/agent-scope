<template>
  <div class="page">
    <h2 class="page-title">管理后台</h2>
    <p class="page-desc">超级管理员专属入口，普通用户视图保持与其他人一致</p>

    <div class="admin-grid">
      <div v-for="item in cards" :key="item.path" class="admin-card" @click="router.push(item.path)">
        <div class="admin-icon">
          <el-icon :size="24"><component :is="item.icon" /></el-icon>
        </div>
        <div class="admin-body">
          <div class="admin-title">{{ item.title }}</div>
          <div class="muted">{{ item.desc }}</div>
        </div>
        <el-icon class="admin-arrow"><ArrowRight /></el-icon>
      </div>
    </div>

    <div v-if="stats" class="panel">
      <h3 class="card-title">用户概览</h3>
      <div class="stat-line">
        <div><span class="muted">总用户</span><b>{{ stats.users.total }}</b></div>
        <div><span class="muted">启用</span><b>{{ stats.users.active }}</b></div>
        <div><span class="muted">管理员</span><b>{{ stats.users.by_role.admin || 0 }}</b></div>
        <div><span class="muted">普通用户</span><b>{{ stats.users.by_role.user || 0 }}</b></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Cpu, Monitor, Setting, UserFilled } from '@element-plus/icons-vue'
import api from '../utils/api'

const router = useRouter()
const stats = ref(null)

const cards = [
  { path: '/admin/users', title: '用户管理', desc: '账号、角色、汇报线与权限配置', icon: UserFilled },
  { path: '/admin/settings', title: '系统配置', desc: '默认设置、角色权限与菜单配置', icon: Setting },
  { path: '/admin/agent', title: 'Agent 配置', desc: '大模型、Embedding 与 Scope 默认参数', icon: Cpu },
  { path: '/system/status', title: '运行信息', desc: 'CPU、内存、GPU、Redis 与网络状态', icon: Monitor }
]

onMounted(async () => {
  try {
    stats.value = await api.get('/admin/stats')
  } catch {
    /* ignore */
  }
})
</script>

<style scoped>
.admin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.admin-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #fff;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 18px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.admin-card:hover {
  border-color: var(--app-primary);
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.08);
}

.admin-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  background: #eff6ff;
  color: var(--app-primary);
  display: grid;
  place-items: center;
  flex: none;
}

.admin-body {
  flex: 1;
}

.admin-title {
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 4px;
}

.admin-arrow {
  color: #94a3b8;
}

.stat-line {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  font-size: 18px;
}

.stat-line div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-title {
  margin: 0 0 14px;
  font-size: 15px;
}

@media (max-width: 767px) {
  .stat-line {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
