<template>
  <div class="page">
    <div class="hero">
      <div>
        <h2 class="hero-title">{{ greeting }}，{{ auth.user?.nickname || auth.user?.username }}</h2>
        <p class="hero-sub">欢迎使用 {{ siteName }}。当前身份：{{ roleLabel }}</p>
      </div>
      <el-tag :type="auth.isSuperAdmin ? 'danger' : auth.isAdmin ? 'warning' : 'info'" effect="dark" round>
        {{ roleLabel }}
      </el-tag>
    </div>

    <div v-if="stats" class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">用户总数</div>
        <div class="stat-value">{{ stats.users.total }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">启用账号</div>
        <div class="stat-value">{{ stats.users.active }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">管理员</div>
        <div class="stat-value">{{ stats.users.by_role.admin || 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">普通用户</div>
        <div class="stat-value">{{ stats.users.by_role.user || 0 }}</div>
      </div>
    </div>

    <div class="panel">
      <h3 class="card-title">快捷入口</h3>
      <div class="quick-grid">
        <div v-for="item in quickLinks" :key="item.path" class="quick-item" @click="router.push(item.path)">
          <el-icon :size="22"><component :is="item.icon" /></el-icon>
          <div>
            <div class="quick-title">{{ item.title }}</div>
            <div class="muted">{{ item.desc }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3 class="card-title">我的权限</h3>
      <div class="perm-list">
        <el-tag v-for="key in auth.permissions" :key="key" type="info" effect="plain">
          {{ permissionName(key) }}
        </el-tag>
        <span v-if="!auth.permissions.length" class="muted">暂无可用权限，请联系管理员</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Setting, User, UserFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import api from '../utils/api'

const auth = useAuthStore()
const router = useRouter()
const stats = ref(null)
const siteName = import.meta.env.VITE_APP_TITLE || 'Agent Scope Platform'

const roleLabels = { super_admin: '超级管理员', admin: '管理员', user: '普通用户' }
const roleLabel = computed(() => roleLabels[auth.user?.role] || '用户')
const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '早上好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const permissionNames = {
  dashboard: '工作台',
  profile: '个人中心',
  'ai.use': '使用 AI',
  'ai.config': 'AI 配置管理',
  'admin.users': '用户管理',
  'admin.settings': '默认配置',
  'admin.permissions': '权限配置'
}
function permissionName(key) {
  return permissionNames[key] || key
}

const quickLinks = computed(() => {
  const links = [
    { path: '/profile', title: '个人中心', desc: '修改资料与密码', icon: User }
  ]
  if (auth.isAdmin || auth.hasPermission('admin.users')) {
    links.unshift({ path: '/admin/users', title: '用户管理', desc: '账号、角色与汇报线', icon: UserFilled })
  }
  if (auth.isSuperAdmin) {
    links.unshift({ path: '/admin/settings', title: '系统配置', desc: '默认配置与角色权限', icon: Setting })
  }
  return links
})

onMounted(async () => {
  if (!auth.isSuperAdmin) return
  try {
    stats.value = await api.get('/admin/stats')
  } catch {
    /* ignore */
  }
})
</script>

<style scoped>
.hero {
  background: linear-gradient(135deg, #1d4ed8, #0ea5e9);
  color: #fff;
  border-radius: 16px;
  padding: 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
}

.hero-title {
  margin: 0;
  font-size: 20px;
}

.hero-sub {
  margin: 6px 0 0;
  opacity: 0.85;
  font-size: 13px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background: #fff;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  padding: 16px;
}

.stat-label {
  color: var(--app-muted);
  font-size: 12px;
}

.stat-value {
  font-size: 26px;
  font-weight: 700;
  margin-top: 6px;
}

.card-title {
  margin: 0 0 12px;
  font-size: 15px;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 12px;
}

.quick-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--app-border);
  cursor: pointer;
  transition: all 0.18s ease;
}

.quick-item:hover {
  border-color: var(--app-primary);
  transform: translateY(-1px);
}

.quick-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 3px;
}

.perm-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 767px) {
  .hero {
    padding: 18px;
    border-radius: 14px;
  }
  .hero-title {
    font-size: 17px;
  }
  .stat-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .stat-value {
    font-size: 22px;
  }
}
</style>
