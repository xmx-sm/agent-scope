import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import api from '../utils/api'
import { useChatStore } from './chat'

function readJSON(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) || fallback
  } catch {
    return fallback
  }
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const user = ref(readJSON('user', null))
  const permissions = ref(readJSON('permissions', []))
  const menus = ref(readJSON('menus', []))

  const isLoggedIn = computed(() => Boolean(accessToken.value))
  const isSuperAdmin = computed(() => user.value?.role === 'super_admin')
  const isAdmin = computed(() => ['super_admin', 'admin'].includes(user.value?.role))

  function persistTokens(data) {
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    user.value = data.user
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('user', JSON.stringify(data.user))
  }

  function persistMe(data) {
    user.value = data.user
    permissions.value = data.permissions || []
    localStorage.setItem('user', JSON.stringify(data.user))
    localStorage.setItem('permissions', JSON.stringify(permissions.value))
  }

  async function login(account, password) {
    const data = await api.post('/auth/login', { account, password })
    persistTokens(data)
    await fetchMe()
    return data
  }

  async function register(payload) {
    const data = await api.post('/auth/register', payload)
    persistTokens(data.tokens)
    await fetchMe()
    return data
  }

  async function fetchMe() {
    const data = await api.get('/auth/me')
    persistMe(data)
    await fetchMenus()
    return data
  }

  async function fetchMenus() {
    menus.value = await api.get('/menus/mine')
    localStorage.setItem('menus', JSON.stringify(menus.value))
    return menus.value
  }

  function hasPermission(key) {
    return permissions.value.includes(key)
  }

  async function logout() {
    const token = refreshToken.value
    accessToken.value = ''
    refreshToken.value = ''
    user.value = null
    permissions.value = []
    menus.value = []
    useChatStore().reset()
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    localStorage.removeItem('permissions')
    localStorage.removeItem('menus')
    if (token) {
      try {
        await api.post('/auth/logout', { refresh_token: token })
      } catch {
        /* 本地状态已清理，网络失败不阻塞退出 */
      }
    }
  }

  return {
    accessToken,
    refreshToken,
    user,
    permissions,
    menus,
    isLoggedIn,
    isSuperAdmin,
    isAdmin,
    login,
    register,
    fetchMe,
    fetchMenus,
    hasPermission,
    logout
  }
})
