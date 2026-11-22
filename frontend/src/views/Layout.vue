<template>
  <el-container class="layout">
    <!-- 桌面侧栏 -->
    <el-aside v-if="!isMobile" :width="collapsed ? '68px' : '224px'" class="sidebar">
      <div class="brand" :class="{ 'brand-collapsed': collapsed }">
        <div class="brand-logo">{{ initials }}</div>
        <div v-if="!collapsed" class="brand-text">
          <div class="brand-name">{{ siteName }}</div>
          <div class="brand-role">{{ roleLabel }}</div>
        </div>
      </div>
      <nav class="menu">
        <template v-for="item in auth.menus" :key="item.key">
          <div v-if="item.children && item.children.length" class="menu-group">
            <div class="menu-group-title" @click="toggleGroup(item.key)">
              <el-icon><component :is="item.icon || 'Menu'" /></el-icon>
              <span class="grow">{{ item.title }}</span>
              <el-icon class="group-arrow" :class="{ folded: isGroupCollapsed(item.key) }">
                <ArrowDown />
              </el-icon>
            </div>
            <router-link
              v-for="child in item.children"
              v-show="!isGroupCollapsed(item.key)"
              :key="child.key"
              :to="child.path"
              class="menu-item menu-item-child"
              :class="{ active: route.path === child.path }"
              @click="drawerVisible = false"
            >
              <el-icon><component :is="child.icon || 'Menu'" /></el-icon>
              <span>{{ child.title }}</span>
            </router-link>
          </div>
          <router-link
            v-else
            :to="item.path"
            class="menu-item"
            :class="{ active: route.path === item.path }"
            @click="drawerVisible = false"
          >
            <el-icon><component :is="item.icon || 'Menu'" /></el-icon>
            <span>{{ item.title }}</span>
          </router-link>
        </template>
      </nav>
      <div v-if="!collapsed" class="sidebar-footer">v0.5.1</div>
    </el-aside>

    <!-- 移动端抽屉 -->
    <el-drawer
      v-if="isMobile"
      v-model="drawerVisible"
      direction="ltr"
      size="78%"
      :with-header="false"
      class="mobile-drawer"
    >
      <div class="brand drawer-brand">
        <div class="brand-logo">{{ initials }}</div>
        <div class="brand-text">
          <div class="brand-name">{{ siteName }}</div>
          <div class="brand-role">{{ roleLabel }}</div>
        </div>
      </div>
      <nav class="menu">
        <router-link
          v-for="item in menus"
          :key="item.path"
          :to="item.path"
          class="menu-item"
          :class="{ active: route.path === item.path }"
          @click="drawerVisible = false"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </router-link>
      </nav>
    </el-drawer>

    <el-container>
      <el-header height="58px" class="topbar">
        <div class="topbar-left">
          <el-button
            v-if="isMobile"
            text
            circle
            :icon="Expand"
            @click="drawerVisible = true"
          />
          <el-button
            v-else
            text
            circle
            :icon="collapsed ? Expand : Fold"
            :title="collapsed ? '展开菜单' : '收起菜单'"
            @click="toggleCollapse"
          />
          <span class="topbar-title">{{ route.meta.title || '工作台' }}</span>
        </div>
        <el-dropdown trigger="click" @command="onCommand">
          <div class="user-chip">
            <el-avatar :size="30" :src="auth.user?.avatar || undefined" class="avatar">
              {{ avatarText }}
            </el-avatar>
            <span class="user-name hide-mobile">{{ auth.user?.nickname || auth.user?.username }}</span>
            <el-icon class="hide-mobile"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人中心</el-dropdown-item>
              <el-dropdown-item command="permissions">我的权限</el-dropdown-item>
              <el-dropdown-item command="menu-settings">菜单个性化</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  ArrowDown,
  Avatar,
  Expand,
  Fold,
  Grid,
  Key,
  Monitor,
  Setting,
  User,
  UserFilled
} from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isMobile = ref(window.innerWidth < 768)
const drawerVisible = ref(false)
const collapsed = ref(localStorage.getItem('sidebar_collapsed') === '1')
const collapsedGroups = ref(new Set(readCollapsedGroups()))
const siteName = ref(import.meta.env.VITE_APP_TITLE || 'Agent Scope')

const roleLabels = { super_admin: '超级管理员', admin: '管理员', user: '普通用户' }
const roleLabel = computed(() => roleLabels[auth.user?.role] || '用户')
const initials = computed(() => (auth.user?.nickname || auth.user?.username || 'AS').slice(0, 2))
const avatarText = computed(() => (auth.user?.nickname || auth.user?.username || 'U').slice(0, 1))

const flatMenus = computed(() =>
  auth.menus.flatMap((item) =>
    item.children && item.children.length ? item.children : [item]
  )
)

function readCollapsedGroups() {
  try {
    return JSON.parse(localStorage.getItem('menu_groups_collapsed') || '[]')
  } catch {
    return []
  }
}

function persistCollapsedGroups() {
  localStorage.setItem('menu_groups_collapsed', JSON.stringify([...collapsedGroups.value]))
}

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar_collapsed', collapsed.value ? '1' : '0')
}

function toggleGroup(key) {
  const next = new Set(collapsedGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedGroups.value = next
  persistCollapsedGroups()
}

function isGroupCollapsed(key) {
  return collapsedGroups.value.has(key)
}

function expandActiveGroup() {
  const parent = auth.menus.find((item) =>
    item.children?.some((child) => child.path === route.path)
  )
  if (!parent) return
  if (collapsedGroups.value.has(parent.key)) {
    const next = new Set(collapsedGroups.value)
    next.delete(parent.key)
    collapsedGroups.value = next
    persistCollapsedGroups()
  }
}

function onResize() {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) drawerVisible.value = false
}

watch(
  () => route.path,
  () => expandActiveGroup()
)

onMounted(() => {
  window.addEventListener('resize', onResize)
  // 每次进入/刷新都以服务端为准，避免 localStorage 里缓存的旧菜单不更新
  if (auth.isLoggedIn) auth.fetchMe().catch(() => {})
  expandActiveGroup()
})
onBeforeUnmount(() => window.removeEventListener('resize', onResize))

async function onCommand(command) {
  if (command === 'profile') {
    router.push('/profile')
    return
  }
  if (command === 'permissions') {
    router.push('/permissions')
    return
  }
  if (command === 'menu-settings') {
    router.push('/menu-settings')
    return
  }
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
    } catch {
      return
    }
    auth.logout()
    router.replace('/login')
  }
}
</script>

<style scoped>
.layout {
  height: 100%;
}

.sidebar {
  background: var(--app-sidebar);
  color: #e5e7eb;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.2s ease;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 18px 16px;
}

.brand-collapsed {
  padding: 18px 0 16px;
  justify-content: center;
}

.drawer-brand {
  padding: 20px 16px;
}

.brand-logo {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  flex: none;
}

.brand-name {
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  line-height: 1.3;
  white-space: nowrap;
}

.brand-role {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

.menu {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 10px;
  color: #cbd5e1;
  font-size: 14px;
  transition: all 0.18s ease;
  white-space: nowrap;
}

.menu-item:hover {
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
}

.menu-item.active {
  background: var(--app-primary);
  color: #fff;
}

.menu-item-collapsed {
  justify-content: center;
  padding: 11px 0;
}

.menu-group {
  margin-top: 6px;
}

.menu-group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px 5px;
  color: #94a3b8;
  font-size: 12px;
  letter-spacing: 0.02em;
  cursor: pointer;
  border-radius: 8px;
  user-select: none;
}

.menu-group-title:hover {
  color: #e5e7eb;
  background: rgba(255, 255, 255, 0.04);
}

.group-arrow {
  font-size: 12px;
  transition: transform 0.18s ease;
}

.group-arrow.folded {
  transform: rotate(-90deg);
}

.menu-item-child {
  padding-left: 30px;
}

.sidebar-footer {
  padding: 14px 18px;
  color: #4b5563;
  font-size: 12px;
}

.topbar {
  background: #fff;
  border-bottom: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.topbar-title {
  font-weight: 600;
  font-size: 15px;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 10px;
}

.user-chip:hover {
  background: #f3f4f6;
}

.avatar {
  background: var(--app-primary);
  font-size: 13px;
}

.user-name {
  font-size: 13px;
  color: var(--app-text);
}

.main {
  padding: 0;
  background: var(--app-bg);
  overflow-y: auto;
}

@media (max-width: 767px) {
  .topbar {
    padding: 0 10px;
  }
}

:deep(.mobile-drawer .el-drawer__body) {
  padding: 0;
  background: var(--app-sidebar);
  display: flex;
  flex-direction: column;
}
</style>
