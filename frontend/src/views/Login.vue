<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-brand">
        <div class="auth-logo">{{ initials }}</div>
        <div>
          <h1 class="auth-title">{{ site.site_name }}</h1>
          <p class="auth-sub">{{ site.site_description || '登录以继续' }}</p>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
        <el-form-item label="账号" prop="account">
          <el-input
            v-model="form.account"
            size="large"
            placeholder="用户名 / 昵称 / 邮箱 / 手机号"
            autocomplete="username"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            show-password
            placeholder="请输入密码"
            autocomplete="current-password"
            :prefix-icon="Lock"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>

      <div class="auth-footer">
        还没有账号？
        <router-link v-if="site.allow_register" to="/register">立即注册</router-link>
        <span v-else>当前未开放注册</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import api from '../utils/api'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref()
const loading = ref(false)
const site = reactive({ site_name: 'Agent Scope', site_description: '', allow_register: true })
const form = reactive({ account: '', password: '' })

const rules = {
  account: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const initials = computed(() => (site.site_name || 'AS').slice(0, 2).toUpperCase())

onMounted(async () => {
  try {
    const data = await api.get('/public/site')
    Object.assign(site, data)
    document.title = data.site_name || 'Agent Scope Platform'
  } catch {
    /* 后端未启动时保持默认文案 */
  }
})

async function submit() {
  if (loading.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await auth.login(form.account.trim(), form.password)
    ElMessage.success('登录成功')
    router.replace(route.query.redirect || '/dashboard')
  } catch {
    /* 错误提示由拦截器统一处理 */
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.submit-btn {
  width: 100%;
  margin-top: 6px;
}
</style>
