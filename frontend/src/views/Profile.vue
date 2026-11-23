<template>
  <div class="page">
    <h2 class="page-title">个人中心</h2>
    <p class="page-desc">维护个人资料与登录密码</p>

    <div class="grid">
      <div class="panel">
        <h3 class="card-title">基本资料</h3>
        <div class="avatar-row">
          <el-avatar :size="64" :src="form.avatar || undefined" class="avatar-preview">
            {{ (auth.user?.nickname || 'U').slice(0, 1) }}
          </el-avatar>
          <div class="grow">
            <div class="muted">头像使用图片 URL，留空则使用文字头像</div>
            <el-input v-model="form.avatar" placeholder="https://example.com/avatar.png" clearable />
          </div>
        </div>
        <el-form :model="form" label-position="top">
          <el-form-item label="用户名">
            <el-input :model-value="auth.user?.username" disabled />
          </el-form-item>
          <el-form-item label="昵称">
            <el-input v-model="form.nickname" placeholder="显示名称" />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="form.email" placeholder="选填" />
          </el-form-item>
          <el-form-item label="手机号">
            <el-input v-model="form.phone" placeholder="选填" />
          </el-form-item>
          <el-button type="primary" :loading="saving" @click="saveProfile">保存资料</el-button>
        </el-form>
      </div>

      <div class="panel">
        <h3 class="card-title">修改密码</h3>
        <el-form ref="pwdRef" :model="pwd" :rules="pwdRules" label-position="top">
          <el-form-item label="原密码" prop="old_password">
            <el-input v-model="pwd.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password">
            <el-input v-model="pwd.new_password" type="password" show-password placeholder="至少 6 位" />
          </el-form-item>
          <el-form-item label="确认新密码" prop="confirm">
            <el-input v-model="pwd.confirm" type="password" show-password />
          </el-form-item>
          <el-button type="warning" :loading="changing" @click="changePassword">修改密码</el-button>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import api from '../utils/api'

const auth = useAuthStore()
const saving = ref(false)
const changing = ref(false)
const pwdRef = ref()

const form = reactive({
  nickname: auth.user?.nickname || '',
  email: auth.user?.email || '',
  phone: auth.user?.phone || '',
  avatar: auth.user?.avatar || ''
})

const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' }
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_r, value, cb) =>
        value === pwd.new_password ? cb() : cb(new Error('两次输入的密码不一致')),
      trigger: 'blur'
    }
  ]
}

async function saveProfile() {
  saving.value = true
  try {
    await api.put('/profile', {
      nickname: form.nickname.trim(),
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
      avatar: form.avatar.trim() || null
    })
    await auth.fetchMe()
    ElMessage.success('资料已更新')
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  try {
    await pwdRef.value.validate()
  } catch {
    return
  }
  changing.value = true
  try {
    await api.post('/auth/change-password', {
      old_password: pwd.old_password,
      new_password: pwd.new_password
    })
    ElMessage.success('密码已修改，请重新登录')
    auth.logout()
    window.location.href = `${import.meta.env.BASE_URL}login`
  } catch {
    /* ignore */
  } finally {
    changing.value = false
  }
}
</script>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}

.card-title {
  margin: 0 0 14px;
  font-size: 15px;
}

.avatar-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
}

.avatar-preview {
  background: var(--app-primary);
  font-size: 24px;
  flex: none;
}

.avatar-row .el-input {
  margin-top: 6px;
}

@media (max-width: 767px) {
  .grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
}
</style>
