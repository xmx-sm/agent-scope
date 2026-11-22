import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { public: true } },
  { path: '/register', name: 'Register', component: () => import('../views/Register.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '工作台', permission: 'dashboard' }
      },
      {
        path: 'permissions',
        name: 'MyPermissions',
        component: () => import('../views/MyPermissions.vue'),
        meta: { title: '我的权限', permission: 'permissions.self' }
      },
      {
        path: 'team/permissions',
        name: 'TeamPermissions',
        component: () => import('../views/TeamPermissions.vue'),
        meta: { title: '团队权限', permission: 'permissions.team' }
      },
      {
        path: 'system/status',
        name: 'SystemStatus',
        component: () => import('../views/SystemStatus.vue'),
        meta: { title: '运行状态', permission: 'system.status' }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('../views/Profile.vue'),
        meta: { title: '个人中心', permission: 'profile' }
      },
      {
        path: 'admin/users',
        name: 'UserManage',
        component: () => import('../views/admin/UserManage.vue'),
        meta: { title: '用户管理', permission: 'admin.users' }
      },
      {
        path: 'admin/settings',
        name: 'AdminSettings',
        component: () => import('../views/admin/Settings.vue'),
        meta: {
          title: '默认设置',
          permission: 'admin.settings',
          superAdminOnly: true
        }
      }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    return auth.isLoggedIn ? '/dashboard' : true
  }
  if (!auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return '/login'
    }
  }
  if (to.meta.superAdminOnly && !auth.isSuperAdmin) {
    return '/dashboard'
  }
  if (to.meta.permission && !auth.hasPermission(to.meta.permission) && !auth.isSuperAdmin) {
    return '/dashboard'
  }
  return true
})

export default router
