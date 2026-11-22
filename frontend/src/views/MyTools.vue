<template>
  <div class="page">
    <h2 class="page-title">我的工具</h2>
    <p class="page-desc">默认全部 AI 工具可用；可以自行关闭，恢复需要上级或超管操作</p>

    <div class="panel" v-loading="loading">
      <div v-for="group in groups" :key="group.name" class="tool-group">
        <div class="tool-group-head">
          <b>{{ group.label }}</b>
          <span class="muted">{{ group.tools.filter((t) => t.enabled).length }}/{{ group.tools.length }}</span>
        </div>
        <div class="muted group-desc">{{ group.description }}</div>
        <div class="tool-list">
          <div v-for="tool in group.tools" :key="tool.name" class="tool-item">
            <div>
              <div class="tool-name">{{ tool.label }}</div>
              <div class="muted tool-desc">{{ tool.description }}</div>
            </div>
            <div class="tool-actions">
              <el-tag v-if="!tool.granted" size="small" type="info" effect="plain">未授权</el-tag>
              <el-switch
                :model-value="tool.enabled"
                :disabled="!tool.granted || savingKey === `${group.name}:${tool.name}`"
                @change="(checked) => toggleTool(group, tool, checked)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../utils/api'

const loading = ref(false)
const savingKey = ref('')
const groups = ref([])

async function load() {
  loading.value = true
  try {
    const data = await api.get('/tools/mine')
    groups.value = data.groups || []
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

async function toggleTool(group, tool, checked) {
  savingKey.value = `${group.name}:${tool.name}`
  try {
    const data = await api.post('/tools/mine/narrow', {
      group: group.name,
      tool: tool.name,
      enabled: checked
    })
    groups.value = data.groups || []
    ElMessage.success(checked ? '已恢复该工具' : '已关闭该工具')
  } catch {
    /* ignore */
  } finally {
    savingKey.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.tool-group {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 10px;
}

.tool-group-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.group-desc {
  font-size: 12px;
  margin-bottom: 8px;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tool-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.tool-name {
  font-size: 13.5px;
  font-weight: 500;
}

.tool-desc {
  font-size: 11.5px;
}

.tool-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
