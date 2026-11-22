<template>
  <div class="page">
    <h2 class="page-title">角色权限</h2>
    <p class="page-desc">页面与菜单访问权限（AI 工具权限在「用户管理 → AI 工具」中配置）</p>

    <div v-loading="loading">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="角色权限决定默认能力；具体用户还可被上级继续收缩或由超管单独授权。"
        class="tip"
      />
      <div class="perm-grid">
        <div v-for="role in roles" :key="role.role" class="panel role-card">
          <div class="role-head">
            <div>
              <div class="role-title">{{ roleLabel(role.role) }}</div>
              <div class="muted">{{ role.role }}</div>
            </div>
            <el-tag :type="roleTag(role.role)" effect="plain">{{ roleLabel(role.role) }}</el-tag>
          </div>
          <el-checkbox-group v-model="role.permissions" :disabled="!role.editable" class="perm-checks">
            <el-checkbox v-for="perm in permissions" :key="perm.key" :value="perm.key" :label="perm.key">
              {{ perm.name }}
              <span class="muted perm-group">{{ perm.group }}</span>
            </el-checkbox>
          </el-checkbox-group>
          <el-button
            type="primary"
            :disabled="!role.editable"
            :loading="savingRole === role.role"
            @click="save(role)"
          >
            保存权限
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../utils/api'

const permissions = ref([])
const roles = ref([])
const loading = ref(false)
const savingRole = ref('')

const roleLabels = { super_admin: '超级管理员', admin: '管理员', user: '普通用户' }
function roleLabel(role) {
  return roleLabels[role] || role
}
function roleTag(role) {
  return role === 'super_admin' ? 'danger' : role === 'admin' ? 'warning' : 'info'
}

async function load() {
  loading.value = true
  try {
    const data = await api.get('/admin/permissions')
    permissions.value = data.permissions
    roles.value = data.roles
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function save(role) {
  savingRole.value = role.role
  try {
    await api.put(`/admin/permissions/${role.role}`, { permissions: role.permissions })
    ElMessage.success('权限已保存')
  } catch {
    /* ignore */
  } finally {
    savingRole.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.tip {
  margin-bottom: 14px;
}

.perm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
}

.role-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.role-title {
  font-weight: 700;
  font-size: 15px;
}

.perm-checks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 16px;
}

.perm-group {
  font-size: 11px;
  margin-left: 6px;
}
</style>
