<template>
  <div class="page">
    <h2 class="page-title">管理下级</h2>
    <p class="page-desc">AI 工具权限：上级只能在超管授予的范围内收窄，不能给下级新增工具</p>

    <div class="panel" v-loading="loading">
      <div v-for="member in members" :key="member.id" class="member-card">
        <div class="member-head">
          <div class="member-avatar">{{ (member.nickname || member.username).slice(0, 1) }}</div>
          <div class="grow">
            <div class="member-name">
              {{ member.nickname }}
              <span class="muted">@{{ member.username }}</span>
            </div>
            <div class="member-tags">
              <el-tag size="small" effect="plain">{{ roleLabel(member.role) }}</el-tag>
              <el-tag size="small" :type="member.mode === 'all' ? 'success' : 'warning'" effect="light">
                {{ member.mode === 'all' ? '全部工具' : '按清单授权' }}
              </el-tag>
              <span class="muted">{{ member.enabled_count }}/{{ member.total_count }} 个工具可用</span>
            </div>
          </div>
          <el-button
            v-if="member.mode === 'all'"
            size="small"
            plain
            :loading="tighteningId === member.id"
            @click="tighten(member)"
          >
            收紧为清单
          </el-button>
          <el-button type="danger" plain size="small" @click="openAdjust(member)">收窄工具</el-button>
        </div>
      </div>
      <el-empty v-if="!members.length && !loading" description="暂无下属成员" />
    </div>

    <el-dialog v-model="dialogVisible" title="收窄下级 AI 工具" :width="isMobile ? '94%' : '620px'">
      <div v-if="target" class="adjust-body">
        <p class="muted">
          正在调整：<b>{{ target.nickname }}</b>。关闭后该工具对下级立即不可用；重新打开只能恢复到超管授权范围。
        </p>
        <div v-for="group in target.groups" :key="group.name" class="tool-group">
          <div class="tool-group-head">
            <b>{{ group.label }}</b>
            <div class="group-actions">
              <span class="muted">
                {{ group.tools.filter((t) => t.enabled).length }}/{{ group.tools.length }}
              </span>
              <el-switch
                :model-value="group.tools.some((t) => t.enabled)"
                :disabled="savingKey === `${group.name}:__group__`"
                size="small"
                @change="(checked) => toggleGroup(group, checked)"
              />
            </div>
          </div>
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
      <template #footer>
        <el-button @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../utils/api'

const isMobile = ref(window.innerWidth < 768)
const loading = ref(false)
const members = ref([])
const dialogVisible = ref(false)
const target = ref(null)
const savingKey = ref('')
const tighteningId = ref('')

const roleLabels = { super_admin: '超级管理员', admin: '管理员', user: '普通用户' }
function roleLabel(role) {
  return roleLabels[role] || role
}

async function load() {
  loading.value = true
  try {
    members.value = await api.get('/tools/team')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function openAdjust(member) {
  target.value = member
  dialogVisible.value = true
}

async function tighten(member) {
  tighteningId.value = member.id
  try {
    const view = await api.post(`/tools/team/${member.id}/tighten`)
    Object.assign(member, {
      mode: view.mode,
      enabled_count: view.enabled_count,
      total_count: view.total_count,
      groups: view.groups
    })
    ElMessage.success('已切换为按清单授权')
  } catch {
    /* ignore */
  } finally {
    tighteningId.value = ''
  }
}

async function toggleGroup(group, checked) {
  savingKey.value = `${group.name}:__group__`
  try {
    const view = await api.post(`/tools/team/${target.value.id}/narrow`, {
      group: group.name,
      tool: '',
      enabled: checked
    })
    target.value.mode = view.mode
    target.value.enabled_count = view.enabled_count
    target.value.total_count = view.total_count
    target.value.groups = view.groups
    const index = members.value.findIndex((item) => item.id === target.value.id)
    if (index >= 0) members.value[index] = target.value
    ElMessage.success(checked ? '已开启该工具组' : '已关闭该工具组')
  } catch {
    /* ignore */
  } finally {
    savingKey.value = ''
  }
}

async function toggleTool(group, tool, checked) {
  const key = `${group.name}:${tool.name}`
  savingKey.value = key
  try {
    const view = await api.post(`/tools/team/${target.value.id}/narrow`, {
      group: group.name,
      tool: tool.name,
      enabled: checked
    })
    target.value = {
      ...target.value,
      mode: view.mode,
      enabled_count: view.enabled_count,
      total_count: view.total_count,
      groups: view.groups
    }
    const index = members.value.findIndex((item) => item.id === target.value.id)
    if (index >= 0) members.value[index] = target.value
    ElMessage.success(checked ? '已恢复该工具' : '已收窄该工具')
  } catch {
    /* ignore */
  } finally {
    savingKey.value = ''
  }
}

onMounted(load)
</script>

<style scoped>
.member-card {
  border-bottom: 1px dashed var(--app-border);
  padding: 14px 0;
}

.member-card:first-child {
  padding-top: 0;
}

.member-card:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.member-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.member-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: #dbeafe;
  color: #1d4ed8;
  display: grid;
  place-items: center;
  font-weight: 700;
  flex: none;
}

.member-name {
  font-weight: 600;
  font-size: 14px;
}

.member-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 5px;
  align-items: center;
}

.adjust-body {
  max-height: 58vh;
  overflow-y: auto;
}

.tool-group {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
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

.group-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 767px) {
  .member-head {
    flex-wrap: wrap;
  }
}
</style>
