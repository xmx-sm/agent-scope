<template>
  <div class="page">
    <h2 class="page-title">我的权限</h2>
    <p class="page-desc">权限只能逐级收缩；如需恢复请联系上级或超级管理员</p>

    <div v-loading="loading">
      <div class="panel">
        <div class="perm-head">
          <div>
            <div class="role-line">
              当前角色：<el-tag effect="plain">{{ roleLabel(detail.role) }}</el-tag>
            </div>
            <div class="muted">共 {{ detail.effective.length }} 项有效权限</div>
          </div>
          <el-button type="primary" plain :icon="Refresh" @click="load">刷新</el-button>
        </div>
        <div class="chip-list">
          <el-tag v-for="key in detail.effective" :key="key" type="success" effect="light">
            {{ nameOf(key) }}
          </el-tag>
          <span v-if="!detail.effective.length" class="muted">暂无权限</span>
        </div>
      </div>

      <div v-if="detail.temp_grants?.length" class="panel">
        <h3 class="card-title">临时越级授权</h3>
        <div class="temp-list">
          <div v-for="item in detail.temp_grants" :key="item.permission" class="temp-item">
            <el-tag type="warning" effect="plain">{{ nameOf(item.permission) }}</el-tag>
            <span class="muted">有效期至 {{ formatTime(item.expires_at) }}</span>
          </div>
        </div>
      </div>

      <div v-if="detail.shrunk?.length" class="panel">
        <h3 class="card-title">已被收缩的权限</h3>
        <div class="chip-list">
          <el-tag v-for="key in detail.shrunk" :key="key" type="info" effect="plain">
            {{ nameOf(key) }}
          </el-tag>
        </div>
      </div>

      <div v-if="toolView" class="panel">
        <h3 class="card-title">AI 工具权限</h3>
        <p class="muted">默认全部工具可用；可以自行关闭，恢复需要上级或超管操作。</p>
        <div v-for="group in toolView.groups" :key="group.name" class="tool-group">
          <div class="tool-group-head">
            <b>{{ group.label }}</b>
            <span class="muted">{{ group.tools.filter((t) => t.enabled).length }}/{{ group.tools.length }}</span>
          </div>
          <div class="tool-list">
            <div v-for="tool in group.tools" :key="tool.name" class="tool-item">
              <span>
                {{ tool.label }}
                <span class="muted tool-desc">{{ tool.description }}</span>
              </span>
              <div class="tool-actions">
                <el-tag v-if="!tool.granted" size="small" type="info" effect="plain">未授权</el-tag>
                <el-switch
                  :model-value="tool.enabled"
                  :disabled="!tool.granted || toolSavingKey === `${group.name}:${tool.name}`"
                  @change="(checked) => toggleTool(group, tool, checked)"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel">
        <h3 class="card-title">收缩自己的页面权限</h3>
        <p class="muted">勾选后保存，这些权限会从你的账号中移除；收缩操作不可自行恢复。</p>
        <div v-if="detail.shrinkable?.length" class="shrink-box">
          <el-checkbox-group v-model="selected">
            <el-checkbox v-for="key in detail.shrinkable" :key="key" :value="key" :label="key">
              {{ nameOf(key) }}
            </el-checkbox>
          </el-checkbox-group>
          <el-button type="danger" :disabled="!selected.length" :loading="saving" @click="shrink">
            收缩所选权限
          </el-button>
        </div>
        <el-empty v-else description="没有可收缩的权限" :image-size="70" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import api from '../utils/api'

const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const selected = ref([])
const detail = ref({ effective: [], shrunk: [], temp_grants: [], shrinkable: [], catalog: [] })
const toolView = ref(null)
const toolSavingKey = ref('')

const roleLabels = { super_admin: '超级管理员', admin: '管理员', user: '普通用户' }
function roleLabel(role) {
  return roleLabels[role] || role
}
function nameOf(key) {
  return detail.value.catalog?.find((item) => item.key === key)?.name || key
}
function formatTime(value) {
  return new Date(value).toLocaleString()
}

async function load() {
  loading.value = true
  try {
    const [pageDetail, tools] = await Promise.all([
      api.get('/permissions/mine'),
      api.get('/tools/mine')
    ])
    detail.value = pageDetail
    toolView.value = tools
    selected.value = []
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function toggleTool(group, tool, checked) {
  toolSavingKey.value = `${group.name}:${tool.name}`
  try {
    toolView.value = await api.post('/tools/mine/narrow', {
      group: group.name,
      tool: tool.name,
      enabled: checked
    })
    ElMessage.success(checked ? '已恢复该工具' : '已关闭该工具')
  } catch {
    /* ignore */
  } finally {
    toolSavingKey.value = ''
  }
}

async function shrink() {
  try {
    await ElMessageBox.confirm(
      `确定收缩所选 ${selected.value.length} 项权限吗？收缩后需要上级或超管才能恢复。`,
      '收缩确认',
      { type: 'warning', confirmButtonText: '确定收缩' }
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await api.post('/permissions/mine/shrink', { permissions: selected.value })
    ElMessage.success('权限已收缩')
    await auth.fetchMe()
    await load()
  } catch {
    /* ignore */
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.perm-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.role-line {
  font-size: 14px;
  margin-bottom: 4px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.temp-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.temp-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-title {
  margin: 0 0 12px;
  font-size: 15px;
}

.tool-group {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 10px;
}

.tool-group-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13.5px;
}

.tool-desc {
  font-size: 11.5px;
  margin-left: 6px;
}

.tool-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.shrink-box {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
}

.shrink-box :deep(.el-checkbox-group) {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
