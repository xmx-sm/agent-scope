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
        path: 'chat',
        name: 'Chat',
        component: () => import('../views/Chat.vue'),
        meta: { title: 'AI 对话', permission: 'ai.use' }
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '工作台', permission: 'dashboard' }
      },
      {
        path: 'my-tools',
        name: 'MyTools',
        component: () => import('../views/MyTools.vue'),
        meta: { title: '我的工具', permission: 'ai.use' }
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
        path: 'tool-settings',
        name: 'ToolConfig',
        component: () => import('../views/ToolConfig.vue'),
        meta: { title: '工具配置', permission: 'ai.use' }
      },
      {
        path: 'agent-knowledge',
        name: 'AgentKnowledge',
        component: () => import('../views/Knowledge.vue'),
        meta: { title: '知识库', permission: 'ai.use' }
      },
      {
        path: 'agent-skills',
        name: 'AgentSkills',
        component: () => import('../views/Skills.vue'),
        meta: { title: 'Skills', permission: 'ai.use' }
      },
      {
        path: 'agent-mcp',
        name: 'AgentMcp',
        component: () => import('../views/McpSettings.vue'),
        meta: { title: 'MCP', permission: 'ai.use' }
      },
      {
        path: 'agent-subagents',
        name: 'AgentSubagents',
        component: () => import('../views/Subagents.vue'),
        meta: { title: '子智能体', permission: 'ai.use' }
      },
      {
        path: 'agent-super',
        name: 'AgentSuper',
        component: () => import('../views/SuperAgent.vue'),
        meta: { title: '超级智能体', permission: 'ai.use' }
      },
      {
        path: 'agent-a2a',
        name: 'AgentA2A',
        component: () => import('../views/A2A.vue'),
        meta: { title: 'A2A 协作', permission: 'ai.use' }
      },
      {
        path: 'tool-approvals',
        name: 'ToolApprovals',
        component: () => import('../views/ToolApprovals.vue'),
        meta: { title: '工具审批', permission: 'permissions.team' }
      },
      {
        path: 'agent-scheduled',
        name: 'AgentScheduled',
        component: () => import('../views/Scheduled.vue'),
        meta: { title: '定时任务', permission: 'ai.use' }
      },
      {
        path: 'agent-memory',
        name: 'AgentMemory',
        component: () => import('../views/Memory.vue'),
        meta: { title: '长期记忆', permission: 'ai.use' }
      },
      {
        path: 'agent-stats',
        name: 'AgentStats',
        component: () => import('../views/AgentStats.vue'),
        meta: { title: 'Agent 统计', permission: 'ai.use' }
      },
      {
        path: 'agent-settings',
        name: 'AgentSelfConfig',
        component: () => import('../views/AgentSelfConfig.vue'),
        meta: { title: 'Agent 设置', permission: 'ai.use' }
      },
      {
        path: 'menu-settings',
        name: 'MenuPersonalize',
        component: () => import('../views/MenuPersonalize.vue'),
        meta: { title: '菜单个性化', permission: 'dashboard' }
      },
      { path: 'admin', redirect: '/admin/users' },
      {
        path: 'admin/users',
        name: 'UserManage',
        component: () => import('../views/admin/UserManage.vue'),
        meta: { title: '用户管理', permission: 'admin.users' }
      },
      {
        path: 'admin/agent',
        name: 'AgentConfig',
        component: () => import('../views/admin/AgentConfig.vue'),
        meta: { title: 'Agent 配置', permission: 'ai.config', superAdminOnly: true }
      },
      {
        path: 'admin/settings',
        redirect: '/admin/config/system'
      },
      {
        path: 'admin/tool-audits',
        name: 'ToolAudits',
        component: () => import('../views/admin/ToolAudits.vue'),
        meta: { title: '工具权限审计', permission: 'admin.audits', superAdminOnly: true }
      },
      {
        path: 'admin/config/system',
        name: 'ConfigurationSystem',
        component: () => import('../views/admin/ConfigurationSystem.vue'),
        meta: { title: '系统设置', permission: 'admin.settings', superAdminOnly: true }
      },
      {
        path: 'admin/config/roles',
        name: 'ConfigurationRoles',
        component: () => import('../views/admin/ConfigurationRoles.vue'),
        meta: { title: '角色权限', permission: 'admin.permissions', superAdminOnly: true }
      },
      {
        path: 'admin/config/menus',
        name: 'ConfigurationMenus',
        component: () => import('../views/admin/ConfigurationMenus.vue'),
        meta: { title: '菜单配置', permission: 'admin.menus', superAdminOnly: true }
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
