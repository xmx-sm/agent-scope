<template>
  <div class="page">
    <h2 class="page-title">我的工具</h2>
    <p class="page-desc">默认全部 AI 工具可用；可以自行关闭，恢复需要上级或超管操作</p>

    <div class="config-links">
      <span class="muted">配置入口：</span>
      <router-link to="/tool-settings">工具配置</router-link>
      <router-link to="/agent-settings">Agent 设置</router-link>
      <router-link to="/tool-settings?tab=super">超级智能体</router-link>
      <router-link to="/agent-knowledge">知识库</router-link>
    </div>

    <div class="panel" v-loading="loading">
      <div v-for="group in groups" :key="group.name" class="tool-group">
        <div class="tool-group-head">
          <b>{{ group.label }}</b>
          <div class="group-head-right">
            <router-link v-if="configTarget(group)" :to="configTarget(group)" class="config-link">
              {{ configTarget(group).label }}
            </router-link>
            <span class="muted">{{ group.tools.filter((t) => t.enabled).length }}/{{ group.tools.length }}</span>
          </div>
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
              <el-tag v-else-if="tool.require_approval && tool.approval_status === 'pending'" size="small" type="warning" effect="plain">
                待审批
              </el-tag>
              <el-tag v-else-if="tool.require_approval && tool.approval_status === 'denied'" size="small" type="danger" effect="plain">
                已拒绝
              </el-tag>
              <el-button
                v-if="tool.granted && tool.require_approval && tool.approval_status !== 'approved'"
                size="small"
                type="primary"
                plain
                :loading="requestingKey === `${group.name}:${tool.name}`"
                @click="requestTool(group, tool)"
              >
                申请使用
              </el-button>
              <el-switch
                :model-value="tool.enabled"
                :disabled="!tool.granted || (tool.require_approval && tool.approval_status !== 'approved') || savingKey === `${group.name}:${tool.name}`"
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
const requestingKey = ref('')
const groups = ref([])

const CONFIG_TARGETS = {
  mail: { label: '配置邮箱', path: '/tool-settings', query: { tab: 'email' } },
  db: { label: '配置数据库', path: '/tool-settings', query: { tab: 'db' } },
  mcp: { label: '配置 MCP', path: '/tool-settings', query: { tab: 'mcp' } },
  a2a: { label: '配置伙伴', path: '/agent-a2a' },
  rag: { label: '配置知识库', path: '/agent-knowledge' }
}

function configTarget(group) {
  return CONFIG_TARGETS[group.name] || null
}

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

async function requestTool(group, tool) {
  requestingKey.value = `${group.name}:${tool.name}`
  try {
    const data = await api.post('/tools/mine/request', {
      group: group.name,
      tool: tool.name,
      reason: ''
    })
    groups.value = data.groups || []
    ElMessage.success('申请已提交，等待审批')
  } catch {
    /* ignore */
  } finally {
    requestingKey.value = ''
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

.config-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 13px;
}

.config-links a,
.config-link {
  color: var(--app-primary);
  text-decoration: none;
}

.config-links a:hover,
.config-link:hover {
  text-decoration: underline;
}

.config-link {
  font-size: 12px;
}

.group-head-right {
  display: flex;
  align-items: center;
  gap: 10px;
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
