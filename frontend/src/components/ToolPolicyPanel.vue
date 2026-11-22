<template>
  <div v-loading="loading">
    <div class="panel">
      <h3 class="card-title">新用户默认工具权限</h3>
      <p class="muted">只影响之后新注册/新建的账号；存量用户请在「用户管理 → AI 工具」单独调整。</p>
      <el-radio-group v-model="mode" class="mode-switch">
        <el-radio-button value="all">全部工具（默认）</el-radio-button>
        <el-radio-button value="custom">按清单授权</el-radio-button>
      </el-radio-group>
      <p class="muted mode-desc">
        {{ mode === 'all'
          ? '新用户默认拥有全部 AI 工具。'
          : '新用户只拥有下方勾选的工具/工具组。' }}
      </p>

      <div class="tool-groups">
        <div v-for="group in groups" :key="group.name" class="tool-group">
          <div class="tool-group-head">
            <el-checkbox
              v-if="mode === 'custom'"
              :model-value="isGroupSelected(group)"
              @change="(checked) => toggleGroup(group, checked)"
            >
              <b>{{ group.label }}</b>
            </el-checkbox>
            <b v-else>{{ group.label }}</b>
            <span class="muted">{{ group.tools.length }} 项</span>
          </div>
          <div class="muted group-desc">{{ group.description }}</div>
          <div class="tool-list">
            <el-checkbox
              v-for="tool in group.tools"
              :key="tool.name"
              :model-value="isToolSelected(group, tool)"
              :disabled="mode !== 'custom'"
              @change="(checked) => toggleTool(group, tool, checked)"
            >
              {{ tool.label }}
              <span class="muted tool-desc">{{ tool.description }}</span>
            </el-checkbox>
          </div>
        </div>
      </div>

      <div class="save-bar">
        <el-button type="primary" :loading="saving" @click="save">保存默认策略</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../utils/api'

const loading = ref(false)
const saving = ref(false)
const mode = ref('all')
const groups = ref([])
const selected = ref(new Set())

function key(group, tool = '') {
  return `${group}|${tool}`
}

function isGroupSelected(group) {
  return selected.value.has(key(group.name))
}

function isToolSelected(group, tool) {
  return selected.value.has(key(group.name)) || selected.value.has(key(group.name, tool.name))
}

function toggleGroup(group, checked) {
  const next = new Set(selected.value)
  next.delete(key(group.name))
  for (const tool of group.tools) next.delete(key(group.name, tool.name))
  if (checked) next.add(key(group.name))
  selected.value = next
}

function toggleTool(group, tool, checked) {
  const next = new Set(selected.value)
  if (next.has(key(group.name))) {
    next.delete(key(group.name))
    for (const item of group.tools) next.add(key(group.name, item.name))
  }
  if (checked) next.add(key(group.name, tool.name))
  else next.delete(key(group.name, tool.name))
  selected.value = next
}

function readSelection(data) {
  const next = new Set()
  for (const group of data.groups || []) {
    if (group.granted) {
      next.add(key(group.name))
      continue
    }
    for (const tool of group.tools || []) {
      if (tool.granted) next.add(key(group.name, tool.name))
    }
  }
  selected.value = next
}

function selectAll() {
  const next = new Set()
  for (const group of groups.value) next.add(key(group.name))
  selected.value = next
}

async function load() {
  loading.value = true
  try {
    const data = await api.get('/admin/tool-policy/defaults')
    mode.value = data.new_user_mode || 'all'
    groups.value = data.groups || []
    if (mode.value === 'all') selectAll()
    else readSelection(data)
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function save() {
  if (mode.value === 'custom' && !selected.value.size) {
    ElMessage.warning('请至少选择一个工具或工具组')
    return
  }
  const items = []
  if (mode.value === 'custom') {
    for (const group of groups.value) {
      if (selected.value.has(key(group.name))) {
        items.push({ group: group.name, tool: '' })
        continue
      }
      for (const tool of group.tools) {
        if (selected.value.has(key(group.name, tool.name))) {
          items.push({ group: group.name, tool: tool.name })
        }
      }
    }
  }
  saving.value = true
  try {
    await api.put('/admin/tool-policy', { new_user_mode: mode.value, items })
    ElMessage.success('默认工具策略已保存')
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
.card-title {
  margin: 0 0 6px;
  font-size: 15px;
}

.mode-switch {
  margin-top: 12px;
}

.mode-desc {
  margin: 8px 0 14px;
  font-size: 12.5px;
}

.tool-groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.tool-group {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 12px;
}

.tool-group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.group-desc {
  font-size: 12px;
  margin: 2px 0 8px;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-desc {
  font-size: 11px;
  margin-left: 6px;
}

.save-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
