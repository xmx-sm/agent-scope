<template>
  <div class="page">
    <h2 class="page-title">系统配置</h2>
    <p class="page-desc">默认配置与角色权限（仅超级管理员）</p>

    <el-tabs v-model="activeTab" class="tabs">
      <el-tab-pane label="系统设置" name="configs">
        <div v-loading="loadingConfigs">
          <div class="config-toolbar">
            <span class="muted">共 {{ configs.length }} 项，按分组折叠展示</span>
            <div class="grow"></div>
            <el-button size="small" @click="expandAllConfigs">全部展开</el-button>
            <el-button size="small" @click="collapseAllConfigs">全部收起</el-button>
          </div>
          <el-collapse v-model="openGroups" class="config-collapse">
            <el-collapse-item v-for="group in configGroups" :key="group.name" :name="group.name">
              <template #title>
                <span class="collapse-title">{{ group.name }}</span>
                <span class="muted collapse-count">{{ group.items.length }} 项</span>
              </template>
              <div v-for="item in group.items" :key="item.key" class="config-row">
                <div class="config-info">
                  <div class="config-label">{{ item.label || item.key }}</div>
                  <div class="muted">{{ item.description }}</div>
                  <code class="config-key">{{ item.key }} = {{ item.default }}</code>
                </div>
                <div class="config-control">
                  <el-switch v-if="item.value_type === 'bool'" v-model="item.value" />
                  <el-input-number
                    v-else-if="item.value_type === 'int' || item.value_type === 'float'"
                    v-model="item.value"
                    :min="0"
                    :step="item.value_type === 'float' ? 0.1 : 1"
                    :precision="item.value_type === 'float' ? 2 : 0"
                    controls-position="right"
                    style="width: 150px"
                  />
                  <el-select
                    v-else-if="item.key === 'default_role'"
                    v-model="item.value"
                    style="width: 150px"
                  >
                    <el-option label="普通用户" value="user" />
                    <el-option label="管理员" value="admin" />
                  </el-select>
                  <el-input
                    v-else-if="item.secret"
                    v-model="item.value"
                    type="password"
                    show-password
                    style="width: 220px"
                  />
                  <el-input v-else v-model="item.value" style="width: 220px" />
                  <el-button type="primary" :loading="savingKey === item.key" @click="saveConfig(item)">
                    保存
                  </el-button>
                  <el-button
                    :loading="resettingKey === item.key"
                    :disabled="item.value === item.default"
                    @click="resetConfig(item)"
                  >
                    恢复默认
                  </el-button>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-tab-pane>

      <el-tab-pane label="角色权限" name="permissions">
        <div v-loading="loadingPermissions">
          <div class="panel perm-note">
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="角色权限用于控制菜单与页面入口；超级管理员固定拥有全部权限。"
            />
          </div>
          <div class="perm-grid">
            <div v-for="role in rolePermissions" :key="role.role" class="panel role-card">
              <div class="role-head">
                <div>
                  <div class="role-title">{{ roleLabel(role.role) }}</div>
                  <div class="muted">{{ role.role }}</div>
                </div>
                <el-tag :type="roleTag(role.role)" effect="plain">{{ roleLabel(role.role) }}</el-tag>
              </div>
              <el-checkbox-group v-model="role.permissions" :disabled="!role.editable" class="perm-checks">
                <el-checkbox
                  v-for="perm in permissionList"
                  :key="perm.key"
                  :value="perm.key"
                  :label="perm.key"
                >
                  {{ perm.name }}
                  <span class="muted perm-group">{{ perm.group }}</span>
                </el-checkbox>
              </el-checkbox-group>
              <el-button
                type="primary"
                :disabled="!role.editable"
                :loading="savingRole === role.role"
                @click="saveRole(role)"
              >
                保存权限
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="菜单配置" name="menus">
        <div class="panel">
          <MenuConfig />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../utils/api'
import MenuConfig from '../../components/MenuConfig.vue'

const activeTab = ref('configs')
const configs = ref([])
const permissionList = ref([])
const rolePermissions = ref([])
const loadingConfigs = ref(false)
const loadingPermissions = ref(false)
const savingKey = ref('')
const resettingKey = ref('')
const savingRole = ref('')
const openGroups = ref([])
const configGroups = computed(() => {
  const groups = new Map()
  for (const item of configs.value) {
    const name = item.group || '其他'
    if (!groups.has(name)) groups.set(name, { name, items: [] })
    groups.get(name).items.push(item)
  }
  return [...groups.values()]
})

const roleLabels = { super_admin: '超级管理员', admin: '管理员', user: '普通用户' }
function roleLabel(role) {
  return roleLabels[role] || role
}
function roleTag(role) {
  return role === 'super_admin' ? 'danger' : role === 'admin' ? 'warning' : 'info'
}

async function loadConfigs() {
  loadingConfigs.value = true
  try {
    configs.value = await api.get('/admin/configs', { params: { domain: 'system' } })
    if (!openGroups.value.length) {
      openGroups.value = ['站点', '账号']
    }
  } catch {
    /* ignore */
  } finally {
    loadingConfigs.value = false
  }
}

async function loadPermissions() {
  loadingPermissions.value = true
  try {
    const data = await api.get('/admin/permissions')
    permissionList.value = data.permissions
    rolePermissions.value = data.roles
  } catch {
    /* ignore */
  } finally {
    loadingPermissions.value = false
  }
}

function expandAllConfigs() {
  openGroups.value = configGroups.value.map((group) => group.name)
}

function collapseAllConfigs() {
  openGroups.value = []
}

async function saveConfig(item) {
  savingKey.value = item.key
  try {
    await api.put(`/admin/configs/${item.key}`, { value: item.value })
    ElMessage.success(`${item.label || item.key} 已保存`)
  } catch {
    /* ignore */
  } finally {
    savingKey.value = ''
  }
}

async function resetConfig(item) {
  resettingKey.value = item.key
  try {
    await api.post(`/admin/configs/${item.key}/reset`)
    ElMessage.success(`${item.label || item.key} 已恢复默认值`)
    item.value = item.default
  } catch {
    /* ignore */
  } finally {
    resettingKey.value = ''
  }
}

async function saveRole(role) {
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

onMounted(() => {
  loadConfigs()
  loadPermissions()
})
</script>

<style scoped>
.tabs {
  margin-top: -6px;
}

.config-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 0;
  border-bottom: 1px dashed var(--app-border);
}

.config-row:last-child {
  border-bottom: none;
}

.config-label {
  font-weight: 600;
  font-size: 14px;
}

.config-key {
  display: inline-block;
  margin-top: 6px;
  font-size: 11.5px;
  color: #64748b;
  background: #f1f5f9;
  border-radius: 5px;
  padding: 1px 6px;
}

.config-control {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}

.config-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.config-collapse {
  border: 1px solid var(--app-border);
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
}

.config-collapse :deep(.el-collapse-item__header) {
  padding: 0 16px;
  background: #fafbfc;
}

.config-collapse :deep(.el-collapse-item__content) {
  padding: 0 16px 12px;
}

.collapse-title {
  font-weight: 700;
  font-size: 14px;
  margin-right: 8px;
}

.collapse-count {
  font-size: 12px;
}

.perm-note {
  padding: 0;
  border: none;
  background: transparent;
  box-shadow: none;
}

.perm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
  margin-top: 14px;
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

@media (max-width: 767px) {
  .config-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  .config-control {
    width: 100%;
  }
  .config-control :deep(.el-input-number),
  .config-control :deep(.el-input),
  .config-control :deep(.el-select) {
    flex: 1;
    width: auto !important;
  }
}
</style>
